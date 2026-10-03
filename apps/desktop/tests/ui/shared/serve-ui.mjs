import { createServer } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { request as httpRequest } from "node:http";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
let backendOrigin = "";
const isolatedBackend = {
  name: "isolated-backend-boundary",
  configureServer(vite) {
    vite.middlewares.use((incoming, outgoing, next) => {
      if (incoming.url === "/__ui__/backend" && incoming.method === "POST") {
        let body = "";
        incoming.on("data", part => { body += String(part); if (body.length > 1024) incoming.destroy(); });
        incoming.on("end", () => {
          try {
            const target = new URL(JSON.parse(body).origin);
            if (target.protocol !== "http:" || target.hostname !== "127.0.0.1" || target.pathname !== "/" || !target.port) throw new Error();
            backendOrigin = target.origin;
            outgoing.writeHead(200, { "Content-Type": "application/json" }).end('{"ready":true}');
          } catch { outgoing.writeHead(400).end("Invalid isolated backend origin."); }
        });
        return;
      }
      if (!/^\/(?:health(?:\?|$)|v1(?:\/|\?|$))/.test(incoming.url ?? "")) return next();
      if (!backendOrigin) { outgoing.writeHead(503).end("No isolated backend is attached."); return; }
      const target = new URL(incoming.url, backendOrigin);
      if (target.origin !== backendOrigin) { outgoing.writeHead(400).end("Only the attached loopback backend is accepted."); return; }
      const headers = { ...incoming.headers }; delete headers.host;
      const upstream = httpRequest(target, { method: incoming.method, headers }, response => {
        outgoing.writeHead(response.statusCode ?? 502, response.headers);
        response.pipe(outgoing);
      });
      upstream.on("error", () => { if (!outgoing.headersSent) outgoing.writeHead(503, { "Content-Type": "application/json" }); outgoing.end('{"detail":"Isolated backend is restarting."}'); });
      outgoing.once("close", () => upstream.destroy());
      incoming.pipe(upstream);
    });
  },
};
const server = await createServer({ root, configFile: false, plugins: [react(), isolatedBackend], server: { host: "127.0.0.1", port: 5173, strictPort: true }, logLevel: "error" });
await server.listen();
process.stdout.write("Isolated renderer ready on 127.0.0.1:5173\n");
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, async () => { await server.close(); process.exit(0); });
