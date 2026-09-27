'use strict';

// Installation-only schema discovery through the official MCP connection and
// SDK. The default upstream browser factory is lazy; no page/action is invoked.
const fs = require('node:fs/promises');
const path = require('node:path');
const { createConnection } = require('@playwright/mcp');
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { InMemoryTransport } = require('@modelcontextprotocol/sdk/inMemory.js');

(async () => {
  const server = await createConnection({
    browser: { launchOptions: { channel: 'chrome', headless: true, executablePath: '__catalogue_must_not_launch_browser__' } },
    capabilities: ['core', 'vision'], webmcp: false, imageResponses: 'omit',
  });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: 'workbench-browser-catalogue', version: '0.0.2' });
  try {
    await server.connect(serverTransport);
    await client.connect(clientTransport);
    const catalogue = await client.listTools();
    await fs.writeFile(path.join(__dirname, 'tool-schemas.json'), JSON.stringify({
      playwright_mcp_version: require('@playwright/mcp/package.json').version,
      worker_version: require('./package.json').version,
      tools: catalogue.tools,
    }, null, 2) + '\n');
  } finally {
    await client.close();
    await server.close();
  }
})().catch(error => { console.error('Browser tool catalogue failed:', error.message); process.exit(1); });
