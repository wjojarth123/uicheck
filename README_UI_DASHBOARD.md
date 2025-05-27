# UI Testing Dashboard

This project consists of a Flask backend and Svelte frontend for automated UI testing and analysis.

## Features

- Browser automation using Playwright and Browser-Use Agent
- Website screenshot capture and analysis
- HTML content analysis
- Interactive sitemap graph visualization
- Color analysis of webpages
- Real-time updates via long polling

## Setup

1. Make sure you have Python and Node.js installed
2. Install Python dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Navigate to the Svelte app directory and install frontend dependencies:
   ```
   cd testpilot
   npm install
   ```

## Running the Application

### Option 1: Run both servers with one command

Run the `start_app.py` script to start both backend and frontend:

```
python start_app.py
```

This will:
- Start the Flask backend server on port 5000
- Start the Svelte dev server on port 5173
- Open your browser to the application

### Option 2: Run servers separately

1. Start the Flask backend:
   ```
   python client_endpoint.py
   ```

2. In a separate terminal, start the Svelte frontend:
   ```
   cd testpilot
   npm run dev -- --host
   ```

3. Open your browser to http://localhost:5173

## How It Works

1. The frontend connects to the backend and receives a connection ID
2. The backend runs an AI agent that navigates websites and captures screenshots, HTML, and other data
3. The frontend polls for new data and displays it in real-time
4. The sitemap graph shows the structure of the website being analyzed

## API Endpoints

- `POST /api/connect` - Create a new connection and get a connection ID
- `GET /api/data/<connection_id>` - Get data for a specific connection (long polling)
- `POST /api/start-agent` - Start the browser agent with a task
- `GET /api/status` - Get the current status of the agent
- `GET /api/graph` - Get the current graph data
- `GET /api/screenshot/<url_hash>` - Get a screenshot by URL hash
- `GET /api/html/<url_hash>` - Get HTML content by URL hash
