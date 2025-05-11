#!/usr/bin/env python3
"""
Results Viewer
---------------
A simple web-based UI for viewing exploration results.
"""

import os
import json
import argparse
from http.server import HTTPServer, SimpleHTTPRequestHandler
import webbrowser
from pathlib import Path
import sys

# Default port for the HTTP server
DEFAULT_PORT = 8000

# HTML template for the results viewer
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Web Explorer Results</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { padding-top: 20px; }
        .screenshot { max-width: 100%; border: 1px solid #ddd; border-radius: 4px; }
        .tree-img { max-width: 100%; border: 1px solid #ddd; border-radius: 4px; }
        .url-box { word-break: break-all; }
        .agent-card { margin-bottom: 20px; }
        .nav-tabs { margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="mb-4">Web Explorer Results</h1>
        
        <ul class="nav nav-tabs" id="resultsTabs" role="tablist">
            <li class="nav-item" role="presentation">
                <button class="nav-link active" id="summary-tab" data-bs-toggle="tab" data-bs-target="#summary" type="button" role="tab">Summary</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="tree-tab" data-bs-toggle="tab" data-bs-target="#tree" type="button" role="tab">Exploration Tree</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="agents-tab" data-bs-toggle="tab" data-bs-target="#agents" type="button" role="tab">Agent Details</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="urls-tab" data-bs-toggle="tab" data-bs-target="#urls" type="button" role="tab">Visited URLs</button>
            </li>
        </ul>
        
        <div class="tab-content" id="resultsTabsContent">
            <!-- Summary Tab -->
            <div class="tab-pane fade show active" id="summary" role="tabpanel">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Exploration Summary</h5>
                        <div class="row">
                            <div class="col-md-6">
                                <p><strong>Start URL:</strong> <span id="summary-start-url"></span></p>
                                <p><strong>Domain:</strong> <span id="summary-domain"></span></p>
                                <p><strong>Start Time:</strong> <span id="summary-start-time"></span></p>
                                <p><strong>Duration:</strong> <span id="summary-duration"></span> seconds</p>
                                <p><strong>URLs Visited:</strong> <span id="summary-urls-count"></span></p>
                            </div>
                            <div class="col-md-6">
                                <img src="exploration_tree.png" class="tree-img" alt="Exploration Tree Preview">
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Tree Tab -->
            <div class="tab-pane fade" id="tree" role="tabpanel">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Exploration Tree</h5>
                        <img src="exploration_tree.png" class="img-fluid" alt="Exploration Tree">
                    </div>
                </div>
            </div>
            
            <!-- Agents Tab -->
            <div class="tab-pane fade" id="agents" role="tabpanel">
                <div class="row">
                    <div class="col-md-4">
                        <div class="list-group" id="agent-list">
                            <!-- Agent list will be populated here -->
                        </div>
                    </div>
                    <div class="col-md-8">
                        <div id="agent-details">
                            <!-- Agent details will be shown here -->
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- URLs Tab -->
            <div class="tab-pane fade" id="urls" role="tabpanel">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Visited URLs</h5>
                        <div class="list-group" id="url-list">
                            <!-- URL list will be populated here -->
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.2.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Load the results data
        fetch('exploration_results.json')
            .then(response => response.json())
            .then(data => {
                // Populate summary tab
                document.getElementById('summary-start-url').textContent = data.start_url;
                document.getElementById('summary-domain').textContent = data.domain;
                document.getElementById('summary-start-time').textContent = data.start_time;
                document.getElementById('summary-duration').textContent = data.duration_seconds.toFixed(2);
                document.getElementById('summary-urls-count').textContent = data.urls_visited;
                
                // Process exploration log to organize by agent
                const agentMap = new Map();
                
                data.exploration_log.forEach(entry => {
                    if (!agentMap.has(entry.agent_id)) {
                        agentMap.set(entry.agent_id, []);
                    }
                    agentMap.get(entry.agent_id).push(entry);
                });
                
                // Populate agent list
                const agentList = document.getElementById('agent-list');
                agentMap.forEach((entries, agentId) => {
                    // Find the agent's URL
                    const agentUrl = entries[0].url;
                    const listItem = document.createElement('a');
                    listItem.href = '#';
                    listItem.className = 'list-group-item list-group-item-action';
                    listItem.textContent = `Agent ${agentId.substring(0, 8)}... - ${new URL(agentUrl).pathname}`;
                    listItem.dataset.agentId = agentId;
                    
                    listItem.addEventListener('click', (e) => {
                        e.preventDefault();
                        
                        // Remove active class from all items
                        document.querySelectorAll('#agent-list a').forEach(item => {
                            item.classList.remove('active');
                        });
                        
                        // Add active class to clicked item
                        listItem.classList.add('active');
                        
                        // Show agent details
                        showAgentDetails(agentId, entries);
                    });
                    
                    agentList.appendChild(listItem);
                });
                
                // Populate URL list
                const urlList = document.getElementById('url-list');
                data.all_urls.forEach(url => {
                    const listItem = document.createElement('a');
                    listItem.href = url;
                    listItem.className = 'list-group-item list-group-item-action url-box';
                    listItem.textContent = url;
                    listItem.target = '_blank';
                    urlList.appendChild(listItem);
                });
                
                // Click the first agent to show its details
                if (agentList.firstChild) {
                    agentList.firstChild.click();
                }
            })
            .catch(error => {
                console.error('Error loading results:', error);
            });
            
        function showAgentDetails(agentId, entries) {
            const agentDetails = document.getElementById('agent-details');
            
            // Clear previous details
            agentDetails.innerHTML = '';
            
            // Create details
            entries.forEach(entry => {
                const card = document.createElement('div');
                card.className = 'card agent-card';
                
                const cardBody = document.createElement('div');
                cardBody.className = 'card-body';
                
                const title = document.createElement('h5');
                title.className = 'card-title';
                title.textContent = new URL(entry.url).pathname;
                
                const urlText = document.createElement('p');
                urlText.className = 'card-text url-box';
                urlText.innerHTML = `<strong>URL:</strong> <a href="${entry.url}" target="_blank">${entry.url}</a>`;
                
                const depthText = document.createElement('p');
                depthText.className = 'card-text';
                depthText.innerHTML = `<strong>Depth:</strong> ${entry.depth}`;
                
                cardBody.appendChild(title);
                cardBody.appendChild(urlText);
                cardBody.appendChild(depthText);
                
                // Add decision information if available
                if (entry.decision) {
                    const decisionHeader = document.createElement('h6');
                    decisionHeader.className = 'card-subtitle mb-2 mt-3';
                    decisionHeader.textContent = 'AI Decision';
                    
                    const reasoningText = document.createElement('p');
                    reasoningText.className = 'card-text';
                    reasoningText.innerHTML = `<strong>Reasoning:</strong> ${entry.decision.reasoning}`;
                    
                    const strategyText = document.createElement('p');
                    strategyText.className = 'card-text';
                    strategyText.innerHTML = `<strong>Strategy:</strong> ${entry.decision.branch_strategy}`;
                    
                    const contentText = document.createElement('p');
                    contentText.className = 'card-text';
                    contentText.innerHTML = `<strong>Interesting Content:</strong> ${entry.decision.interesting_content}`;
                    
                    cardBody.appendChild(decisionHeader);
                    cardBody.appendChild(reasoningText);
                    cardBody.appendChild(strategyText);
                    cardBody.appendChild(contentText);
                }
                
                // Add screenshot if available
                const screenshotPath = `${agentId}.png`;
                
                // We need to check if the file exists
                const img = new Image();
                img.className = 'screenshot mt-3';
                img.src = screenshotPath;
                img.alt = 'Page Screenshot';
                
                // Add error handler
                img.onerror = function() {
                    this.style.display = 'none';
                };
                
                cardBody.appendChild(img);
                
                card.appendChild(cardBody);
                agentDetails.appendChild(card);
            });
        }
    </script>
</body>
</html>
"""

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="View web exploration results in a browser"
    )
    
    parser.add_argument(
        "--port", 
        type=int, 
        default=DEFAULT_PORT,
        help=f"HTTP server port (default: {DEFAULT_PORT})"
    )
    
    parser.add_argument(
        "--dir",
        default="exploration_results",
        help="Directory containing exploration results (default: exploration_results)"
    )
    
    return parser.parse_args()

def create_index_html(results_dir):
    """Create the index.html file for viewing results"""
    index_path = os.path.join(results_dir, "index.html")
    with open(index_path, "w") as f:
        f.write(HTML_TEMPLATE)
    return index_path

def start_server(results_dir, port):
    """Start the HTTP server for viewing results"""
    # Change to the results directory
    os.chdir(results_dir)
    
    # Create a custom handler that sets CORS headers
    class CORSRequestHandler(SimpleHTTPRequestHandler):
        def end_headers(self):
            self.send_header('Access-Control-Allow-Origin', '*')
            super().end_headers()
    
    # Create and start the server
    server = HTTPServer(('localhost', port), CORSRequestHandler)
    print(f"Server started at http://localhost:{port}")
    print("Press Ctrl+C to stop the server")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Server stopped")
        server.server_close()

def main():
    """Main entry point"""
    args = parse_args()
    
    # Validate results directory
    results_dir = os.path.abspath(args.dir)
    if not os.path.isdir(results_dir):
        print(f"Error: Results directory not found: {results_dir}")
        return 1
    
    # Check for results file
    results_file = os.path.join(results_dir, "exploration_results.json")
    if not os.path.isfile(results_file):
        print(f"Error: Results file not found: {results_file}")
        return 1
    
    # Create index.html
    index_path = create_index_html(results_dir)
    
    # Open in browser
    url = f"http://localhost:{args.port}/"
    print(f"Opening results viewer at {url}")
    webbrowser.open(url)
    
    # Start server
    start_server(results_dir, args.port)
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 