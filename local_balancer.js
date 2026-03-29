// Local Round-Robin Load Balancer for Python Flask Workers
// Runs on the Linux Board. Exposes Port 4000.
// Cloudflare Tunnel routes public traffic exactly to this Port 4000.

const http = require('http');

const FLASK_PORTS = [5000, 5001, 5002, 5003, 5004, 5005, 5006];
const HOST = 'localhost';
const BALANCER_PORT = 4000;

let currentPortIndex = 0;

const server = http.createServer((req, res) => {
    let targetPort;

    // Route system management API calls to the local Python Service Manager
    if (req.url.startsWith('/api/system/')) {
        targetPort = 8080;
    } else {
        // Select the next Flask port in the round-robin cycle
        targetPort = FLASK_PORTS[currentPortIndex];
        currentPortIndex = (currentPortIndex + 1) % FLASK_PORTS.length;
    }

    const options = {
        hostname: HOST,
        port: targetPort,
        path: req.url,
        method: req.method,
        headers: req.headers
    };

    // Forward request to specific Flask instance
    const proxyReq = http.request(options, (proxyRes) => {
        res.writeHead(proxyRes.statusCode, proxyRes.headers);
        proxyRes.pipe(res, { end: true });
    });

    proxyReq.on('error', (err) => {
        console.error(`Load Balancer Error targeting port ${targetPort}:`, err.message);
        res.writeHead(502);
        res.end('Flask worker unreachable.');
    });

    req.pipe(proxyReq, { end: true });
});

server.listen(BALANCER_PORT, '0.0.0.0', () => {
    console.log(`===============================================`);
    console.log(`Local Python Load Balancer Running!`);
    console.log(`Routing inbound traffic aggressively to:`);
    console.log(`Ports 5000 -> 5006`);
    console.log(`-----------------------------------------------`);
    console.log(`Cloudflare Tunnel Target URL: http://localhost:${BALANCER_PORT}`);
    console.log(`===============================================`);
});
