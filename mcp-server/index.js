import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { google } from "googleapis";
import { z } from "zod";
import dotenv from "dotenv";

dotenv.config();

// setup gmail auth using refresh token
const auth = new google.auth.OAuth2(
  process.env.GOOGLE_CLIENT_ID,
  process.env.GOOGLE_CLIENT_SECRET
);

auth.setCredentials({
  refresh_token: process.env.GOOGLE_REFRESH_TOKEN,
});

const gmail = google.gmail({ version: "v1", auth });

// create MCP server
const server = new McpServer({
  name: "gmail-mcp-server",
  version: "1.1.0",
});

function header(headers, name) {
  const lower = name.toLowerCase();
  return headers?.find((h) => h.name.toLowerCase() === lower)?.value;
}

// Wrap a tool handler so Gmail/API failures come back as MCP errors
// (isError: true) with a readable message, instead of a crashed request.
function safe(handler) {
  return async (args) => {
    try {
      return await handler(args);
    } catch (err) {
      const message = err?.response?.data?.error?.message || err?.message || String(err);
      return { isError: true, content: [{ type: "text", text: message }] };
    }
  };
}

// ── TOOL 1: List emails ──────────────────────────────────────────
server.tool(
  "gmail_list_messages",
  "List emails matching a Gmail search query. Returns id, thread id, sender, subject and date for each.",
  {
    query: z.string().optional().describe("Gmail search query e.g. is:unread, from:alice, newer_than:7d"),
    maxResults: z.number().int().min(1).max(50).optional().describe("Max number of emails to fetch (default 5)"),
  },
  safe(async ({ query = "in:inbox", maxResults = 5 }) => {
    const res = await gmail.users.messages.list({
      userId: "me",
      q: query,
      maxResults,
    });

    const messages = res.data.messages || [];

    if (messages.length === 0) {
      return {
        content: [{ type: "text", text: "No emails found." }],
      };
    }

    // fetch full details for each message
    const detailed = await Promise.all(
      messages.map(async (msg) => {
        const full = await gmail.users.messages.get({
          userId: "me",
          id: msg.id,
          format: "metadata",
          metadataHeaders: ["Subject", "From", "Date"],
        });

        const headers = full.data.payload?.headers;
        const subject = header(headers, "Subject") || "No Subject";
        const from = header(headers, "From") || "Unknown";
        const date = header(headers, "Date") || "Unknown";

        return `ID: ${msg.id}\nThread: ${msg.threadId}\nFrom: ${from}\nSubject: ${subject}\nDate: ${date}`;
      })
    );

    return {
      content: [{ type: "text", text: detailed.join("\n\n---\n\n") }],
    };
  })
);

// ── helpers for body extraction ──────────────────────────────────
function decodeBase64Url(data) {
  if (!data) return "";
  return Buffer.from(data, "base64url").toString("utf-8");
}

function findPartByMime(node, mime) {
  if (!node) return null;
  if (node.mimeType === mime && node.body?.data) return node;
  for (const p of node.parts || []) {
    const m = findPartByMime(p, mime);
    if (m) return m;
  }
  return null;
}

function htmlToText(html) {
  return html
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|h[1-6]|li|tr|td|blockquote)>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function extractBody(payload) {
  const plain = findPartByMime(payload, "text/plain");
  if (plain) return decodeBase64Url(plain.body.data);

  const html = findPartByMime(payload, "text/html");
  if (html) return htmlToText(decodeBase64Url(html.body.data));

  if (payload.body?.data) {
    const raw = decodeBase64Url(payload.body.data);
    return payload.mimeType?.startsWith("text/html") ? htmlToText(raw) : raw;
  }
  return "";
}

// ── TOOL 2: Read full email ──────────────────────────────────────
server.tool(
  "gmail_read_message",
  "Read the full content of a specific email by ID",
  {
    messageId: z.string().describe("The Gmail message ID"),
  },
  safe(async ({ messageId }) => {
    const res = await gmail.users.messages.get({
      userId: "me",
      id: messageId,
      format: "full",
    });

    const headers = res.data.payload?.headers;
    const subject = header(headers, "Subject") || "No Subject";
    const from = header(headers, "From") || "Unknown";
    const date = header(headers, "Date") || "Unknown";

    const body = extractBody(res.data.payload ?? {});

    return {
      content: [
        {
          type: "text",
          text: `From: ${from}\nDate: ${date}\nSubject: ${subject}\nThread: ${res.data.threadId}\n\nBody:\n${body}`,
        },
      ],
    };
  })
);

// ── helpers for sending ──────────────────────────────────────────
// Header values must not contain CR/LF, otherwise a crafted subject or
// recipient could inject extra headers (e.g. Bcc) into the message.
function headerSafe(value) {
  return String(value).replace(/[\r\n]+/g, " ").trim();
}

// RFC 2047 encoding so non-ASCII subjects (accents, emoji) aren't mangled.
function encodeHeaderWord(value) {
  // eslint-disable-next-line no-control-regex
  if (/^[\x00-\x7F]*$/.test(value)) return value;
  return `=?UTF-8?B?${Buffer.from(value, "utf-8").toString("base64")}?=`;
}

// ── TOOL 3: Send email ───────────────────────────────────────────
server.tool(
  "gmail_send_message",
  "Send an email via Gmail. To reply within an existing conversation, pass the original message's id as replyToMessageId.",
  {
    to: z.string().describe("Recipient email address"),
    subject: z.string().describe("Email subject"),
    body: z.string().describe("Email body text"),
    replyToMessageId: z
      .string()
      .optional()
      .describe("Gmail message ID being replied to; keeps the reply in the same thread"),
  },
  safe(async ({ to, subject, body, replyToMessageId }) => {
    const headers = [
      `To: ${headerSafe(to)}`,
      `Subject: ${encodeHeaderWord(headerSafe(subject))}`,
      "MIME-Version: 1.0",
      "Content-Type: text/plain; charset=utf-8",
      "Content-Transfer-Encoding: base64",
    ];

    let threadId;
    if (replyToMessageId) {
      const original = await gmail.users.messages.get({
        userId: "me",
        id: replyToMessageId,
        format: "metadata",
        metadataHeaders: ["Message-ID", "References"],
      });
      threadId = original.data.threadId;
      const origHeaders = original.data.payload?.headers;
      const messageIdHeader = header(origHeaders, "Message-ID");
      if (messageIdHeader) {
        const refs = [header(origHeaders, "References"), messageIdHeader]
          .filter(Boolean)
          .join(" ");
        headers.push(`In-Reply-To: ${headerSafe(messageIdHeader)}`);
        headers.push(`References: ${headerSafe(refs)}`);
      }
    }

    // Body is base64-encoded (wrapped at 76 chars) so any UTF-8 text and
    // long lines survive transport intact.
    const encodedBody = Buffer.from(body, "utf-8")
      .toString("base64")
      .replace(/(.{76})/g, "$1\r\n");
    const rawMessage = [...headers, "", encodedBody].join("\r\n");

    await gmail.users.messages.send({
      userId: "me",
      requestBody: {
        raw: Buffer.from(rawMessage, "utf-8").toString("base64url"),
        ...(threadId ? { threadId } : {}),
      },
    });

    return {
      content: [{ type: "text", text: `Email sent to ${to} successfully.` }],
    };
  })
);

// ── TOOL 4: Get thread ───────────────────────────────────────────
server.tool(
  "gmail_get_thread",
  "Get every message in an email thread (sender, date, subject, body) for context before replying",
  {
    threadId: z.string().describe("The Gmail thread ID"),
  },
  safe(async ({ threadId }) => {
    const res = await gmail.users.threads.get({
      userId: "me",
      id: threadId,
      format: "full",
    });

    const messages = res.data.messages || [];
    const summary = messages.map((msg) => {
      const headers = msg.payload?.headers;
      const subject = header(headers, "Subject") || "";
      const from = header(headers, "From") || "";
      const date = header(headers, "Date") || "";
      const body = extractBody(msg.payload ?? {});
      return `ID: ${msg.id}\nFrom: ${from}\nDate: ${date}\nSubject: ${subject}\n\n${body}`;
    });

    return {
      content: [{ type: "text", text: summary.join("\n\n---\n\n") }],
    };
  })
);

// start server
const transport = new StdioServerTransport();
await server.connect(transport);
console.error("Gmail MCP Server running...");