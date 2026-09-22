#!/usr/bin/env node
// Zero-dependency static server for local preview: node web/serve.js [port]

const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const PORT = Number(process.argv[2] || process.env.PORT || 8777);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.jsonl': 'application/x-ndjson; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
};

http.createServer((req, res) => {
  const requested = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  const target = path.join(ROOT, requested === '/' ? 'index.html' : requested);

  // Keep the server pinned inside web/ even if the path contains ../
  if (!path.resolve(target).startsWith(ROOT + path.sep) && path.resolve(target) !== ROOT) {
    res.writeHead(403).end('Forbidden');
    return;
  }

  fs.readFile(target, (error, data) => {
    if (error) {
      res.writeHead(404, { 'Content-Type': 'text/plain' }).end('Not found');
      return;
    }
    res.writeHead(200, {
      'Content-Type': TYPES[path.extname(target)] || 'application/octet-stream',
      'Cache-Control': 'no-cache',
    }).end(data);
  });
}).listen(PORT, () => {
  console.log(`Solana Growth Tracker dashboard: http://localhost:${PORT}`);
});
