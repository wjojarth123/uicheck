<script>
  import { onMount, onDestroy } from 'svelte';
  import * as d3 from 'd3';
  import { Network } from 'vis-network';

  // State variables
  let connectionId = null;  let status = 'Disconnected';
  let currentUrl = '';
  let screenshotUrl = '';
  let uniqueColors = 0;
  let graph = { nodes: [], edges: [] };
  let activeSection = 'metrics';
  let isAgentRunning = false;
  let taskInput = 'go to everfi.com log in as a student, using my google account 100034323@mvla.net Complete a mental health lesson, and interact with the questions there, as if you were a student.';
  let zoomLevel = 1;
  let currentPageFontConsistencyScore = null; // New state variable for font score
  let showConnectionModal = true;
  let timelineEvents = [];
  let networkInstance;

  let panOffset = { x: 0, y: 0 };
  let isDragging = false;
  let dragStartPos = { x: 0, y: 0 };
  let colorAnalysisActive = false;
  let colorData = [];  let currentColorPalette = { 
    prominent_colors: [], 
    color_ranges: [],
    cohesiveness_score: 0,
    color_score: 0 // Changed from palette_quality_score to color_score
  };  let sitePalette = { 
    site_palette: [], 
    total_images_analyzed: 0,
    color_score: 0,
    avg_page_score: 0, 
    avg_font_consistency_score: 0,
    neural_score: 0, 
    alignment_score: 0 
  };
  let currentFontGroups = {}; // Added for direct font group data
  let colorSortBy = 'quality';  // 'quality' or 'colors'
  let visualizationMode = 'palette'; // 'palette' or 'font'
  
  // Element references for D3
  let graphContainer;

  $: currentGraphNode = graph.nodes.find(n => n.id === currentUrl);

  onMount(async () => {
    // Auto-connect disabled, we'll connect through the modal
    // Poll for agent status
    getAgentStatus();
    // Get site-wide color palette
    getSitePalette();
  });

  onDestroy(() => {
    // Cleanup code if needed
  });  async function connectToBackend() {
    try {
      status = 'Connecting...';
      const response = await fetch('/api/connect', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          task: taskInput.trim()
        })
      });
      
      const data = await response.json();
      connectionId = data.connection_id;
      status = 'Connected';
      console.log(`Connected with ID: ${connectionId}`);
      
      // Start polling for data immediately after connection
      pollForData();
      
      showConnectionModal = false;
    } catch (error) {
      status = 'Connection Failed';
      console.error('Failed to connect:', error);
    }
  }  async function pollForData() {
    if (!connectionId) return;
    
    try {
      const response = await fetch(`/api/data/${connectionId}`);
      const data = await response.json();
      
      if (data.status === 'waiting') {
        console.log('Waiting for new data...');
      } else if (data.status === 'idle' || data.status === 'active' || data.status === 'error') {
        console.log('Received new data:', data);
        isAgentRunning = data.status === 'active';
        
        if (data.current_url) {
          currentUrl = data.current_url;
        }

        if (data.map) {
          if (graph && graph.nodes && graph.nodes.length === data.map.nodes.length && JSON.stringify(graph.edges) === JSON.stringify(data.map.edges)) {
            // More granular update to preserve Svelte reactivity if only node data changed
            let nodesChanged = false;
            const newNodes = data.map.nodes.map((newNode, index) => {
              if (JSON.stringify(newNode) !== JSON.stringify(graph.nodes[index])) {
                nodesChanged = true;
                return newNode;
              }
              return graph.nodes[index];
            });
            if (nodesChanged) {
              graph = { ...data.map, nodes: newNodes };
              renderNetwork(); 
            }
          } else {
            graph = data.map;
            renderNetwork(); 
          }
          
          if (activeSection === 'metrics') {
            refreshColorData();
          }
        }
        
        if (data.latest_screenshot_data) {
          screenshotUrl = `data:image/png;base64,${data.latest_screenshot_data}`;
        }
        
        if (data.latest_color_palette) {
          currentColorPalette = data.latest_color_palette;
        }

        if (data.latest_font_groups) { // Update currentFontGroups directly
          currentFontGroups = data.latest_font_groups;
        } else {
          currentFontGroups = {}; // Clear if not present
        }
        
        // Existing logic to update font groups within the graph nodes (can remain for other UI parts)
        if (data.latest_font_groups && data.current_url && graph && graph.nodes) {
          const nodeIndex = graph.nodes.findIndex(n => n.id === data.current_url);
          if (nodeIndex !== -1) {
            if (!graph.nodes[nodeIndex].grouped_font_sizes || 
                JSON.stringify(graph.nodes[nodeIndex].grouped_font_sizes) !== JSON.stringify(data.latest_font_groups)) {
                
                const newNodes = graph.nodes.map(n => {
                    if (n.id === data.current_url) {
                        return { ...n, grouped_font_sizes: data.latest_font_groups };
                    }
                    return n;
                });
                graph = { ...graph, nodes: newNodes };
            }
          }
        }
        
        if (data.pages && data.pages.length > 0) {
          const latestPage = data.pages.find(p => p.url === data.current_url) || data.pages[data.pages.length - 1];
          
          if (latestPage && latestPage.metrics) {
            addTimelineEvent({
              time: new Date().toLocaleTimeString(),
              url: latestPage.url,
              colorScore: latestPage.metrics.color || 0, 
              fontScore: (latestPage.metrics.font || 0), 
              neuralScore: latestPage.metrics.neural || 0,
              alignmentScore: latestPage.metrics.alignment || 0
            });
            
            uniqueColors = latestPage.metrics.color || 0;
            currentPageFontConsistencyScore = latestPage.metrics.font || 0;
          }
        }
        
        if (data.sitewide_metrics) {
          sitePalette = {
            ...sitePalette, // preserve other potential fields if any
            total_images_analyzed: graph.nodes?.length || data.pages?.length || 0,
            color_score: data.sitewide_metrics.color || 0,
            avg_font_consistency_score: data.sitewide_metrics.font || 0, 
            neural_score: data.sitewide_metrics.neural || 0,
            alignment_score: data.sitewide_metrics.alignment || 0
          };
          console.log('Site metrics updated from data poll:', sitePalette);
        }
      }
    } catch (error) {
      console.error('Error polling for data:', error);
      status = 'Connection Error';
    }
    
    setTimeout(pollForData, 1000);
  }
  
  function addTimelineEvent(event) {
    // Add new event and limit to last 10 events
    timelineEvents = [event, ...timelineEvents.slice(0, 9)];
  }

  async function getAgentStatus() {
    // We'll use connectToBackend to get status
    // Before connection, we just display as idle
    if (connectionId) {
      return;
    }
    
    // Not connected yet, display as idle
    isAgentRunning = false;
    // We won't poll for status until we establish a connection
  }
  async function getLatestScreenshot() {
    // If we're not connected, we can't fetch data
    if (!connectionId) {
      console.log('Not connected, cannot fetch latest data');
      return;
    }
    
    try {
      // If connected, force polling for new data
      const response = await fetch(`/api/data/${connectionId}`);
      if (!response.ok) {
        console.error('Error fetching latest data:', response.statusText);
        return;
      }
      
      const data = await response.json();
      
      // Process the data as in pollForData()
      // Update the agent status
      isAgentRunning = data.status === 'active';
      
      // Update the graph
      if (data.map) {
        graph = data.map;
        renderNetwork();
        
        // Refresh color data for metrics view
        if (activeSection === 'metrics') {
          refreshColorData();
        }
      }
      
      // Update current URL and screenshot
      if (data.current_url) {
        currentUrl = data.current_url;
      }
      
      // Update screenshot if available
      if (data.latest_screenshot_data) {
        screenshotUrl = `data:image/png;base64,${data.latest_screenshot_data}`;
      }
      
      // Update color palette if available
      if (data.latest_color_palette) {
        currentColorPalette = data.latest_color_palette;
      }
      
      // Show a success message
      status = 'Updated to latest data';
      setTimeout(() => {
        status = connectionId ? 'Connected' : 'Disconnected';
      }, 3000);
    } catch (error) {
      console.error('Error fetching latest data:', error);
      status = 'Error fetching data';
      setTimeout(() => {
        status = connectionId ? 'Connected' : 'Disconnected';
      }, 3000);
    }
  }
    async function getSitePalette() {
    // If we're not connected, we can't fetch data
    if (!connectionId) {
      console.log('Not connected, cannot fetch site palette');
      return;
    }
    
    try {
      // Use the existing connection to get data
      const response = await fetch(`/api/data/${connectionId}`);
      if (!response.ok) {
        console.error('Error fetching site palette:', response.statusText);
        return;
      }
      
      const data = await response.json();
      
      // Process site-wide metrics from the response
      if (data.sitewide_metrics) {
        sitePalette = {
          site_palette: [], // We don't have this in the simplified structure
          total_images_analyzed: data.pages.length,
          color_score: data.sitewide_metrics.color || 0,
          avg_page_score: data.sitewide_metrics.color || 0,
          avg_font_consistency_score: data.sitewide_metrics.font || 0
        };
        
        console.log('Site palette updated:', sitePalette);
      }
    } catch (error) {
      console.error('Error fetching site palette:', error);
    }
  }
  async function startAgent() {
    // This is now handled by the connectToBackend function
    if (!connectionId) {
      connectToBackend();
    }
  }
  function renderNetwork() {
    if (!graphContainer || !graph || !graph.nodes || !graph.edges) return;
    
    // Clear previous graph
    while (graphContainer.firstChild) {
      graphContainer.removeChild(graphContainer.firstChild);
    }
    
    // Prepare data for vis-network
    const nodes = graph.nodes.map(node => ({
      id: node.id,
      label: node.id.split('/').pop() || node.id,
      title: `${node.id}<br>Color: ${node.metrics?.color?.toFixed(1) || 0}/10<br>Font: ${node.metrics?.font?.toFixed(1) || 0}/10<br>Neural: ${node.metrics?.neural?.toFixed(1) || 0}/10<br>Alignment: ${node.metrics?.alignment?.toFixed(1) || 0}/10`,
      color: {
        background: node.color || '#4dabf7',
        border: '#1864ab',
        highlight: {
          background: '#339af0',
          border: '#1c7ed6'
        }
      },
      font: { size: 12 },
      size: 16 + (node.metrics?.color ? node.metrics.color * 2 : 0)
    }));
    
    const edges = graph.edges.map(edge => ({
      from: edge.source.id || edge.source,
      to: edge.target.id || edge.target,
      arrows: 'to',
      width: 2,
      color: { color: '#868e96', highlight: '#495057', hover: '#495057' },
      smooth: { type: 'dynamic' }
    }));
    
    // Create network
    const data = { nodes, edges };
    
    const options = {
      physics: {
        stabilization: true,
        barnesHut: {
          gravitationalConstant: -80,
          springConstant: 0.01,
          springLength: 100
        }
      },
      layout: {
        randomSeed: 1,
        improvedLayout: true
      },
      interaction: {
        navigationButtons: true,
        keyboard: true,
        hover: true
      },
      nodes: {
        shape: 'dot',
        scaling: {
          min: 10,
          max: 30
        }
      }
    };
    
    // Create and draw network
    networkInstance = new Network(graphContainer, data, options);
    
    // Add click event listener
    networkInstance.on('click', (params) => {
      if (params.nodes.length > 0) {
        const clickedNodeId = params.nodes[0];
        const node = graph.nodes.find(n => n.id === clickedNodeId);
        
        if (node) {
          currentUrl = node.id;
          uniqueColors = node.metrics?.color || 0;
          currentPageFontConsistencyScore = node.metrics?.font || 0;          // Since we simplified the API, just use the clicked node data
          // If it's the current URL, we already have the latest screenshot
          if (node.id === currentUrl) {
            // We already have the current screenshot
          } else {
            // For non-current URLs, we don't currently have a way to get their screenshots in the simplified API
            // So we'll need to navigate to that URL by triggering a page visit in the agent
            console.log(`Selected node with URL: ${node.id}`);
          }
        }
      }
    });
  }
    // Helper function to create a hash of a URL
  function hashUrl(url) {
    // Simplified implementation that won't match backend MD5 hashing
    // Just for display purposes - we'll look up real hashes from the global data
    // In a production app, we'd use MD5 implementation here
    let str = '';
    for (let i = 0; i < url.length; i++) {
      str += url.charCodeAt(i);
    }
    return str;
  }
    // Find the URL hash from the pages data
  function getUrlHash(url) {
    // In the simplified version, we don't need URL hashes anymore
    // because we're using base64 data directly
    return hashUrl(url);
  }
    // Refresh color data array for the color analysis view
  function refreshColorData() {
    if (!graph || !graph.nodes) return;
    
    colorData = graph.nodes
      .filter(node => node.metrics) 
      .map(node => ({
        url: node.id,
        colorScore: node.metrics.color || 0,
        fontScore: node.metrics.font || 0, 
        neuralScore: node.metrics.neural || 0,
        alignmentScore: node.metrics.alignment || 0,
        urlHash: getUrlHash(node.id) 
      }))
      .sort((a, b) => b.colorScore - a.colorScore); 
  }
  function changeSection(section) {
    activeSection = section;
    
    if (section === 'metrics') {
      refreshColorData();
    } else if (section === 'network') {
      // Re-render the network when switching to this section
      setTimeout(renderNetwork, 100);
    }
  }
</script>

{#if showConnectionModal}
  <!-- Connection Modal -->
  <div class="modal-overlay">
    <div class="modal-container">
      <h2>UI Analysis Dashboard</h2>
      <p>Enter a task for the agent to perform and click Connect to begin</p>
      
      <div class="modal-content">
        <textarea 
          bind:value={taskInput} 
          placeholder="Enter agent task here... (e.g., visit a website and analyze its UI)"
        ></textarea>
        
        <button 
          on:click={connectToBackend}
          disabled={status === 'Connecting...'}
          class="primary-button"
        >
          {status === 'Connecting...' ? 'Connecting...' : 'Connect & Start'}
        </button>
        
        {#if status === 'Connection Failed'}
          <div class="error-message">
            Failed to connect to the backend. Please try again.
          </div>
        {/if}
      </div>
    </div>
  </div>
{:else}
  <!-- Main Application UI -->
  <div class="dashboard-container">
    <header>
      <div class="logo">
        <h1>UI Analysis Dashboard</h1>
        <div class="status-indicator {isAgentRunning ? 'active' : ''}"></div>
      </div>
      
      <div class="timeline">
        {#if timelineEvents.length > 0}
          <div class="timeline-events">
            {#each timelineEvents as event}
              <div class="timeline-event">
                <span class="time">{event.time}</span>
                <span class="event-url">{event.url.split('/').slice(-1)[0] || event.url}</span>
                <div class="event-metrics">
                  <span class="color-count" title="Color Score">{event.colorScore?.toFixed(1)}</span>
                  <span class="font-score" title="Font Score">{event.fontScore?.toFixed(1)}</span>
                </div>
              </div>
            {/each}
          </div>
        {:else}
          <div class="timeline-empty">
            Timeline will appear as the agent visits pages
          </div>
        {/if}
      </div>
      
      <div class="status-bar">
        <span>Status: {isAgentRunning ? 'Active' : 'Idle'}</span>
        <span>Connection: {status}</span>
        {#if currentUrl}
          <span class="current-url" title={currentUrl}>Current: {currentUrl.split('/').pop() || currentUrl}</span>
        {/if}
        <button class="refresh-button" on:click={getLatestScreenshot}>
          Refresh Data
        </button>
      </div>
    </header>

    <div class="main-content">
      <div class="left-panel">
        <div class="screenshot-section">
          <h3>Current Page</h3>
          <div class="screenshot-container">
            {#if screenshotUrl}
              <img src={screenshotUrl} alt="Current page screenshot" />
            {:else}
              <div class="placeholder">No screenshot available yet</div>
            {/if}
          </div>
        </div>
        
        <!-- Visualization section between screenshot and site map -->
        <div class="visualization-section">
          <div class="visualization-header">
            <h3>{visualizationMode === 'palette' ? 'Color Palette' : 'Page Font Palette'}</h3>
            <button class="toggle-button" on:click={() => visualizationMode = visualizationMode === 'palette' ? 'font' : 'palette'}>
              <span class="toggle-arrow">➤</span>
              <span class="toggle-label">{visualizationMode === 'palette' ? 'Show Fonts' : 'Show Palette'}</span>
            </button>
          </div>
          
          
          {#if visualizationMode === 'palette'}
            <!-- Color palette visualization -->
            <div class="palette-display">
              {#if currentColorPalette && currentColorPalette.prominent_colors && currentColorPalette.prominent_colors.length > 0}
                {#each currentColorPalette.prominent_colors.slice(0, 6) as color}
                  <div 
                    class="color-block" 
                    style="background-color: {color.color};" 
                    title="{(color.percentage * 100).toFixed(1)}%"
                  >
                    <!-- Optionally, display color hex or percentage inside the block -->
                    <!-- <span class="color-info">{color.color}</span> -->
                  </div>
                {/each}
              {:else}
                <div class="placeholder">No palette data available for current page ({currentUrl || 'N/A'})</div>
              {/if}
            </div>
          {:else}
            <!-- Font size visualization -->
            <div class="font-size-visualization">
              {#if currentFontGroups && Object.keys(currentFontGroups).length > 0}
                {#each Object.entries(currentFontGroups) as [size, count]}
                  <div class="font-size-group">
                    <div class="font-size-sample" style="font-size: {Math.min(32, Math.max(10, parseInt(size)))}px">Aa</div>
                    <div class="font-size-info">{size}px ({count})</div>
                  </div>
                {/each}
              {:else}
                <div class="placeholder">No font data available for current page ({currentUrl || 'N/A'})</div>
              {/if}
            </div>
          {/if}
        </div>
        
        <div class="sitemap-section">
          <h3>Site Map</h3>
          <div class="network-container" bind:this={graphContainer}></div>
        </div>
      </div>
      
      <div class="right-panel">
        <!-- Site-wide metrics -->
        <div class="site-metrics">
          <h3>Site-wide Metrics</h3>
          
          <div class="metrics-header">
            <div>
              <p>Based on {sitePalette.total_images_analyzed || 0} analyzed pages</p>
            </div>
            
            <div class="metrics-actions">
              <button class="small-button" on:click={getSitePalette}>
                Refresh
              </button>
            </div>
          </div>
          
          <div class="metrics-cards">
            <div class="metric-card">
              <h4>Color Quality</h4>
              <div class="big-score">
                {sitePalette.color_score?.toFixed(1) || 'N/A'}
                <span class="out-of">/10</span>
              </div>
              <div class="score-bar" style="width: {(sitePalette.color_score || 0) * 10}%; background: linear-gradient(90deg, #ff5555, #ffaa55, #55aa55)"></div>
            </div>
            
            <div class="metric-card">
              <h4>Font Consistency</h4>
              <div class="big-score">
                {(sitePalette.avg_font_consistency_score)?.toFixed(1) || 'N/A'} 
                <span class="out-of">/10</span>
              </div>
              <div class="score-bar" style="width: {(sitePalette.avg_font_consistency_score || 0) * 10}%; background: #aa77dd"></div>
            </div>
          </div>
          
          <div class="metrics-cards">
            <div class="metric-card">
              <h4>Neural Score</h4>
              <div class="big-score">
                {sitePalette.neural_score?.toFixed(1) || 'N/A'}
                <span class="out-of">/10</span>
              </div>
              <div class="score-bar" style="width: {(sitePalette.neural_score || 0) * 10}%; background: #5c7cfa"></div>
            </div>
            
            <div class="metric-card">
              <h4>Alignment Score</h4>
              <div class="big-score">
                {sitePalette.alignment_score?.toFixed(1) || 'N/A'}
                <span class="out-of">/10</span>
              </div>
              <div class="score-bar" style="width: {(sitePalette.alignment_score || 0) * 10}%; background: #20c997"></div>
            </div>
          </div>
        </div>
        
        <!-- Color analysis table -->
        <div class="color-table-section">
          <div class="table-header">
            <h3>Page Analysis</h3>
            
            <div class="sort-controls">
              <span>Sort by:</span>
              <button 
                class:active={colorSortBy === 'quality'} 
                on:click={() => colorSortBy = 'quality'}
              >
                Quality
              </button>
              <button 
                class:active={colorSortBy === 'colors'} 
                on:click={() => colorSortBy = 'colors'}
              >
                Colors
              </button>
            </div>
          </div>
          
          {#if graph && graph.nodes && graph.nodes.length > 0}
            <div class="table-container">
              <table class="color-table">
                <thead>
                  <tr>
                    <th>Page</th>
                    <th>Color</th>
                    <th>Font</th>
                    <th>Neural</th>
                    <th>Alignment</th>
                  </tr>
                </thead>
                <tbody>
                  {#each graph.nodes
                    .filter(n => n.metrics && n.timestamp && n.timestamp > 0) // Ensure node has metrics and a valid timestamp
                    .sort((a, b) => {
                      const aColor = a.metrics?.color || 0;
                      const bColor = b.metrics?.color || 0;
                      const aFont = (a.metrics?.font || 0); // Scale for sort comparison
                      const bFont = (b.metrics?.font || 0); // Scale for sort comparison
                      if (colorSortBy === 'quality') {
                        return bColor - aColor;
                      } else { 
                        return bFont - aFont; 
                      }
                    }) as node}
                    <tr 
                      on:click={() => {
                        currentUrl = node.id;
                        uniqueColors = node.metrics?.color || 0;
                        currentPageFontConsistencyScore = node.metrics?.font || 0;
                      }}
                    >
                      <td class="url-cell">
                        <div class="url-wrapper" title={node.id}>
                          {node.id.split('/').pop() || node.id}
                        </div>
                      </td>
                      <td class="score-cell">
                        <div class="score-pill quality-score" 
                          style="background: linear-gradient(90deg,
                            {(node.metrics?.color || 0) < 4 ? '#ff5555' : 
                             (node.metrics?.color || 0) < 7 ? '#ffaa55' : '#55aa55'})">
                          {node.metrics?.color?.toFixed(1) || 'N/A'}
                        </div>
                      </td>
                      <td class="score-cell">
                        {((node.metrics?.font || 0))?.toFixed(1) || 'N/A'}
                      </td>                      <td class="score-cell">
                        <div class="score-pill neural-score">
                          {node.metrics?.neural?.toFixed(1) || 'N/A'}
                        </div>
                      </td>
                      <td class="score-cell">
                        {node.metrics?.alignment?.toFixed(1) || 'N/A'}
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else}
            <div class="placeholder centered">No page analysis data available yet</div>
          {/if}
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  /* Modern CSS Reset */
  *,
  *::before,
  *::after {
    box-sizing: border-box;
  }

  /* Custom Properties for Blue-Pink Gradient */
  :root {
    --color-primary-blue: #2a6af3;
    --color-secondary-blue: #457af9;
    --color-light-blue: #e1ebff;
    --color-primary-pink: #e94b97;
    --color-secondary-pink: #f06ca9;
    --color-light-pink: #ffedf6;
    --gradient-primary: linear-gradient(135deg, var(--color-primary-blue), var(--color-primary-pink));
    --gradient-subtle: linear-gradient(135deg, var(--color-light-blue), var(--color-light-pink));
    --shadow-sm: 0 2px 4px rgba(0, 0, 0, 0.05);
    --shadow-md: 0 4px 8px rgba(0, 0, 0, 0.07);
    --radius-sm: 6px;
    --radius-md: 8px;
    --radius-lg: 12px;
    --transition-standard: all 0.2s ease;
  }

  /* Base Styles and Reset */  :global(body) {
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
    background: linear-gradient(135deg, #f8faff, #fcfaff);
    color: #333;
    line-height: 1.6;
    min-height: 100vh;
  }

  h1, h2, h3, h4, h5 {
    margin: 0;
    font-weight: 600;
  }
  
  /* Modal Styles */
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(0, 0, 0, 0.6);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1000;
    backdrop-filter: blur(3px);
  }
  
  .modal-container {
    background-color: white;
    border-radius: 8px;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
    width: 500px;
    max-width: 90%;
    padding: 2rem;
    animation: fadeIn 0.3s ease-out;
  }
  
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(-20px); }
    to { opacity: 1; transform: translateY(0); }
  }
  
  .modal-container h2 {
    font-size: 1.8rem;
    margin-bottom: 0.5rem;
    color: #2c3e50;
  }
  
  .modal-container p {
    color: #7f8c8d;
    margin-bottom: 1.5rem;
  }
  
  .modal-content {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  
  .modal-content textarea {
    height: 120px;
    padding: 0.75rem;
    border-radius: 6px;
    border: 1px solid #ddd;
    font-size: 1rem;
    resize: none;
    font-family: inherit;
    background-color: #f8f9fb;
    transition: border-color 0.2s;
  }
  
  .modal-content textarea:focus {
    outline: none;
    border-color: #3498db;
    box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2);
  }

  .primary-button {
    background-color: #3498db;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 0.75rem;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: background-color 0.2s, transform 0.1s;
  }
  
  .primary-button:hover {
    background-color: #2980b9;
  }
  
  .primary-button:active {
    transform: translateY(1px);
  }
  
  .primary-button:disabled {
    background-color: #95a5a6;
    cursor: not-allowed;
  }
  
  .error-message {
    color: #e74c3c;
    background-color: rgba(231, 76, 60, 0.1);
    padding: 0.5rem;
    border-radius: 4px;
    font-size: 0.9rem;
    border-left: 3px solid #e74c3c;
  }
  
  /* Dashboard Layout */
  .dashboard-container {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }
  
  header {
    background-color: white;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .logo {
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 1rem;
  }
  
  .logo h1 {
    font-size: 1.5rem;
    color: #2c3e50;
  }
  
  .status-indicator {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background-color: #ccc;
  }
  
  .status-indicator.active {
    background-color: #2ecc71;
    box-shadow: 0 0 5px rgba(46, 204, 113, 0.6);
    animation: pulse 2s infinite;
  }
  
  @keyframes pulse {
    0% { box-shadow: 0 0 0 0 rgba(46, 204, 113, 0.6); }
    70% { box-shadow: 0 0 0 5px rgba(46, 204, 113, 0); }
    100% { box-shadow: 0 0 0 0 rgba(46, 204, 113, 0); }
  }
  
  .timeline {
    background-color: #f8f9fa;
    border-radius: 6px;
    overflow-x: auto;
    white-space: nowrap;
    padding: 0.5rem;
    border: 1px solid #eee;
  }
  
  .timeline-events {
    display: flex;
    gap: 0.5rem;
  }
  
  .timeline-event {
    display: inline-flex;
    flex-direction: column;
    background-color: white;
    border-radius: 4px;
    padding: 0.5rem;
    min-width: 140px;
    border: 1px solid #e0e0e0;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    transition: transform 0.2s;
  }
  
  .timeline-event:hover {
    transform: translateY(-2px);
    box-shadow: 0 3px 6px rgba(0, 0, 0, 0.1);
  }
  
  .time {
    font-size: 0.7rem;
    color: #7f8c8d;
  }
  
  .event-url {
    font-weight: 600;
    font-size: 0.85rem;
    text-overflow: ellipsis;
    overflow: hidden;
  }
  
  .event-metrics {
    display: flex;
    justify-content: space-between;
    margin-top: 0.3rem;
    font-size: 0.75rem;
  }
  
  .color-count {
    background-color: #e74c3c;
    color: white;
    border-radius: 3px;
    padding: 1px 4px;
  }
  
  .font-score {
    background-color: #9b59b6;
    color: white;
    border-radius: 3px;
    padding: 1px 4px;
  }
  
  .timeline-empty {
    text-align: center;
    padding: 1rem;
    color: #95a5a6;
    font-style: italic;
  }
  
  .status-bar {
    display: flex;
    align-items: center;
    gap: 1rem;
    font-size: 0.8rem;
    padding: 0.5rem 1rem;
    background-color: #f1f3f5;
    border-radius: 6px;
  }
  
  .current-url {
    flex-grow: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-family: monospace;
  }
    .refresh-button {
    padding: 0.2rem 0.6rem;
    background-color: white;
    color: #333;
    border: 1px solid transparent;
    border-radius: 4px;
    font-size: 0.8rem;
    cursor: pointer;
    position: relative;
    transition: all 0.2s ease;
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.05);
    z-index: 1;
  }
  
  .refresh-button::before {
    content: "";
    position: absolute;
    top: -2px;
    left: -2px;
    right: -2px;
    bottom: -2px;
    border-radius: 6px;
    padding: 2px;
    background: linear-gradient(135deg, #2193b0, #6dd5ed, #cc2b5e);
    -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
    z-index: -1;
  }
  
  .refresh-button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  }
  
  .main-content {
    display: flex;
    flex-grow: 1;
    overflow: hidden;
  }
    .left-panel {
    width: 33%;
    display: flex;
    flex-direction: column;
    border-right: 1px solid rgba(0, 0, 0, 0.03);
    overflow: auto;
    box-shadow: 2px 0 10px rgba(0, 0, 0, 0.02);
    z-index: 2;
  }
  
  .right-panel {
    width: 67%;
    display: flex;
    flex-direction: column;
    overflow: auto;
    background-color: #f8fafc;
  }
  
  /* Left Panel Sections */
  .screenshot-section {
    padding: 1rem;
    border-bottom: 1px solid #e0e0e0;
  }
    .screenshot-section h3 {
    margin-bottom: 1rem;
    color: #2c3e50;
    font-weight: 600;
    position: relative;
    padding-left: 12px;
  }
  
  .screenshot-section h3::before {
    content: "";
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    height: 18px;
    width: 4px;
    background-image: linear-gradient(to bottom, #2193b0, #cc2b5e);
    border-radius: 4px;
  }
    .screenshot-container {
    max-height: 50vh;
    overflow: auto;
    border: 1px solid rgba(0, 0, 0, 0.04);
    border-radius: 10px;
    background-color: white;
    margin-bottom: 1rem;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.03);
    transition: all 0.3s ease;
  }
  
  .screenshot-container:hover {
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.07);
  }
  
  .screenshot-container img {
    width: 100%;
    display: block;
  }
  
  .page-metrics {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    margin-top: 0.5rem;
  }
    .metric {
    background-color: white;
    border-radius: 6px;
    padding: 0.75rem;
    box-shadow: 0 3px 10px rgba(0, 0, 0, 0.04);
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: calc(50% - 0.5rem);
    transition: all 0.2s ease;
    border: 1px solid rgba(0,0,0,0.03);
  }
  
  .metric:hover {
    transform: translateY(-2px);
    box-shadow: 0 5px 15px rgba(0, 0, 0, 0.08);
  }
  
  .metric-label {
    font-size: 0.7rem;
    color: #7f8c8d;
    margin-bottom: 0.3rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  
  .metric-value {
    font-size: 1.2rem;
    font-weight: bold;
    background: linear-gradient(90deg, #2193b0, #cc2b5e);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  
  .sitemap-section {
    padding: 1rem;
    flex-grow: 1;
    display: flex;
    flex-direction: column;
  }
    .sitemap-section h3 {
    margin-bottom: 1rem;
    color: #2c3e50;
    font-weight: 600;
    position: relative;
    padding-left: 12px;
  }
  
  .sitemap-section h3::before {
    content: "";
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    height: 18px;
    width: 4px;
    background-image: linear-gradient(to bottom, #2193b0, #cc2b5e);
    border-radius: 4px;
    color: #2c3e50;
  }
  
  .network-container {
    flex-grow: 1;
    border: 1px solid #ddd;
    border-radius: 4px;
    background-color: #f8f9fa;
    position: relative;
    height: 300px; /* Minimum height */
  }
  
  /* Right Panel Sections */
  .site-metrics {
    padding: 1.5rem;
    background-color: white;
    border-bottom: 1px solid #e0e0e0;
  }
  
  .site-metrics h3 {
    margin-bottom: 1rem;
    color: #2c3e50;
  }
  
  .metrics-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 1rem;
  }
  
  .metrics-header p {
    margin: 0;
    color: #7f8c8d;
    font-size: 0.9rem;
  }
  
  .metrics-actions {
    display: flex;
    gap: 0.5rem;
  }
  
  .small-button {
    background-color: #f1f3f5;
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 0.2rem 0.5rem;
    font-size: 0.75rem;
    cursor: pointer;
    color: #555;
  }
  
  .small-button:hover {
    background-color: #e9ecef;
  }
  
  .metrics-cards {
    display: flex;
    gap: 1.5rem;
    margin-bottom: 1.5rem;
  }
    .metric-card {
    background-color: white;
    border-radius: 10px;
    padding: 1.25rem;
    flex: 1;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.04);
    position: relative;
    overflow: hidden;
    transition: all 0.3s ease;
    border: 1px solid rgba(0,0,0,0.02);
  }
  
  .metric-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
  }
  
  .metric-card h4 {
    font-size: 0.85rem;
    margin-bottom: 0.75rem;
    color: #7f8c8d;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    font-weight: 600;
  }
  
  .big-score {
    font-size: 2.5rem;
    font-weight: bold;
    color: #2c3e50;
    margin-bottom: 0.75rem;
    transition: all 0.3s ease;
  }
  
  /* Special styling for Neural Score */
  .metric-card:nth-child(1) .big-score {
    background: linear-gradient(90deg, #2193b0, #cc2b5e);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  
  .out-of {
    font-size: 1rem;
    color: #95a5a6;
    font-weight: normal;
  }
    .score-bar {
    height: 6px;
    border-radius: 3px;
    background-image: linear-gradient(90deg, #2193b0, #6dd5ed, #cc2b5e);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    transition: width 0.5s ease-out;
  }
  
  .site-palette-display {
    display: flex;
    height: 40px;
    border-radius: 6px;
    overflow: hidden;
    margin-top: 1rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }
  
  .site-color-block {
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .site-color-code {
    font-size: 0.7rem;
    background-color: rgba(255, 255, 255, 0.7);
    padding: 2px 4px;
    border-radius: 2px;
    font-family: monospace;
    opacity: 0;
    transition: opacity 0.2s;
  }
  
  .site-color-block:hover .site-color-code {
    opacity: 1;
  }
  
  .color-table-section {
    padding: 1.5rem;
    flex-grow: 1;
    display: flex;
    flex-direction: column;
  }
  
  .table-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }
  
  .sort-controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.8rem;
  }
  
  .sort-controls button {
    background: none;
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 0.2rem 0.6rem;
    font-size: 0.8rem;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  
  .sort-controls button:hover {
    background-color: #f1f3f5;
  }
  
  .sort-controls button.active {
    background-color: #3498db;
    color: white;
    border-color: #2980b9;
  }
  
  .table-container {
    background-color: white;
    border-radius: 6px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    overflow: hidden;
    margin-bottom: 1.5rem;
  }
  
  .color-table {
    width: 100%;
    border-collapse: collapse;
  }
  
  .color-table th {
    padding: 0.75rem;
    text-align: left;
    color: #495057;
    border-bottom: 1px solid #e0e0e0;
    font-weight: 600;
    position: relative;
    cursor: pointer;
    user-select: none;
  }
  
  .color-table th::after {
    content: "⇅";
    position: absolute;
    right: 8px;
    color: #adb5bd;
    opacity: 0.5;
    font-size: 0.8rem;
  }
  
  .color-table th.sorted-asc::after {
    content: "↑";
    color: #2193b0;
    opacity: 1;
  }
  
  .color-table th.sorted-desc::after {
    content: "↓";
    color: #cc2b5e;
    opacity: 1;
  }
  
  .color-table th:hover::after {
    opacity: 1;
  }
  
  .color-table td {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid #f1f3f5;
    font-size: 0.9rem;
  }
  
  .color-table tr:hover {
    background-color: rgba(33, 147, 176, 0.03);
    cursor: pointer;
  }
  
  .color-table tr {
    transition: all 0.2s ease;
  }
  
  .color-table tr:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05);
    position: relative;
    z-index: 5;
  }
  
  .url-cell {
    max-width: 280px;
  }
  
  .url-wrapper {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  .score-cell {
    width: 80px;
    text-align: center;
  }
  
  .count-cell {
    width: 60px;
    text-align: center;
    font-weight: bold;
  }
  
  .palette-preview-cell {
    width: 180px;
  }
  
  .palette-preview {
    display: flex;
    gap: 2px;
  }
  
  .mini-color-block {
    height: 24px;
    flex: 1;
    border-radius: 2px;
  }
    .score-pill {
    display: inline-block;
    padding: 0.2rem 0.5rem;
    border-radius: 20px;
    color: white;
    font-weight: bold;
    font-size: 0.8rem;
    text-shadow: 0 0 1px rgba(0, 0, 0, 0.3);
    text-align: center;
    min-width: 28px;
    background-image: linear-gradient(135deg, #2193b0, #6dd5ed, #cc2b5e);
    background-size: 200% 200%;
    animation: gradient-shift 5s ease infinite;
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
  }
  
  @keyframes gradient-shift {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
  }
  
  .selected-page-palette {
    background-color: white;
    border-radius: 6px;
    padding: 1rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  }
  
  .selected-page-palette h4 {
    margin-bottom: 0.75rem;
    font-size: 0.9rem;
    color: #7f8c8d;
  }
    .palette-display {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    padding: 0.75rem;
    background: linear-gradient(135deg, rgba(33, 147, 176, 0.03), rgba(204, 43, 94, 0.03));
    border-radius: 8px;
    border: 1px solid rgba(0, 0, 0, 0.02);
  }
    .color-block {
    height: 42px;
    flex: 1;
    min-width: 80px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
    transition: all 0.2s ease;
    border: 2px solid rgba(255, 255, 255, 0.2);
    outline: 1px solid rgba(0, 0, 0, 0.05);
  }
  
  .color-block:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
  }
  
  .color-code {
    font-size: 0.7rem;
    background-color: rgba(255, 255, 255, 0.7);
    padding: 2px 4px;
    border-radius: 2px;
    font-family: monospace;
  }
  
  .placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 200px;
    color: #95a5a6;
    font-style: italic;
  }
  
  .placeholder.centered {
    height: 150px;
    background-color: white;
    border-radius: 6px;
  }
  
  /* Visualization Section Styles */
  .visualization-section {
    padding: 1rem;
    border-bottom: 1px solid #e0e0e0;
  }
  
  .visualization-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }
    .toggle-button {
    display: flex;
    align-items: center;
    background-color: white;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 0.4rem 0.8rem;
    font-size: 0.75rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    position: relative;
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.05);
    z-index: 1;
  }
  
  .toggle-button::before {
    content: "";
    position: absolute;
    top: -1px;
    left: -1px;
    right: -1px;
    bottom: -1px;
    border-radius: 7px;
    padding: 1px;
    background: linear-gradient(135deg, #2193b0, #6dd5ed, #cc2b5e);
    -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
    z-index: -1;
  }
  
  .toggle-button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.08);
  }
  
  .toggle-arrow {
    margin-right: 0.4rem;
    font-size: 0.7rem;
    transform: rotate(90deg);
    display: inline-block;
  }
  
  .font-size-visualization {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    padding: 0.5rem;
    background-color: #f8f9fa;
    border-radius: 6px;
    border: 1px solid #e0e0e0;
  }
  
  .font-size-group {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 65px;
    padding: 0.75rem 0.5rem;
    background-color: white;
    border-radius: 8px;
    box-shadow: 0 3px 10px rgba(0,0,0,0.04);
    transition: all 0.2s ease;
    border: 1px solid rgba(0,0,0,0.02);
    position: relative;
    overflow: hidden;
  }
  
  .font-size-group::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 3px;
    background: linear-gradient(90deg, #2193b0, #cc2b5e);
  }
  
  .font-size-group:hover {
    transform: translateY(-2px);
    box-shadow: 0 5px 15px rgba(0,0,0,0.07);
  }
  
  .font-size-sample {
    margin-bottom: 0.3rem;
  }
  
  .font-size-info {
    font-size: 0.7rem;
    color: #7f8c8d;
  }
  
  .neural-score {
    background-image: linear-gradient(135deg, #2193b0, #6dd5ed, #cc2b5e);
    background-size: 200% 200%;
    animation: gradient-shift 5s ease infinite;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  }
</style>
