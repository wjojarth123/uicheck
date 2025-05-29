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
    alignment_score: 0,    click_heat: 0
  };
  let currentFontGroups = {}; // Added for direct font group data
  let colorSortBy = 'quality';  // 'quality' or 'colors'
  let leftPanelMode = 'sitemap'; // 'sitemap' or 'heatmap'
  let heatmapImage = ''; // Store the heatmap image data
  
  // Sorting state
  let sortField = '';
  let sortDirection = 'desc'; // 'asc' or 'desc'
  
  // Accordion state for left panel sections
  let accordionState = {
    screenshot: true,
    palette: true,
    fonts: true,
    sitemap: true,
    heatmap: true
  };
  
  // Track changes to leftPanelMode to re-render the network when needed
  $: if (leftPanelMode === 'sitemap') {
    // Use setTimeout to ensure the DOM has updated
    setTimeout(renderNetwork, 50);
  }
  
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
  });

  function sortTable(field) {
    if (sortField === field) {
      sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
      sortField = field;
      sortDirection = 'desc';
    }
  }

  function getSortedNodes(nodes) {
    if (!sortField) {
      // Default sort by neural score descending
      return nodes.sort((a, b) => {
        const aNeural = a.metrics?.neural || 0;
        const bNeural = b.metrics?.neural || 0;
        return bNeural - aNeural;
      });
    }

    return nodes.sort((a, b) => {
      let aValue, bValue;
      
      switch (sortField) {
        case 'page':
          aValue = a.id;
          bValue = b.id;
          break;
        case 'neural':
          aValue = a.metrics?.neural || 0;
          bValue = b.metrics?.neural || 0;
          break;
        case 'heat':
          aValue = a.click_heat || 0;
          bValue = b.click_heat || 0;
          break;
        case 'color':
          aValue = a.metrics?.color || 0;
          bValue = b.metrics?.color || 0;
          break;
        case 'font':
          aValue = a.metrics?.font || 0;
          bValue = b.metrics?.font || 0;
          break;
        case 'alignment':
          aValue = a.metrics?.alignment || 0;
          bValue = b.metrics?.alignment || 0;
          break;
        default:
          return 0;
      }

      if (typeof aValue === 'string') {
        return sortDirection === 'asc' ? aValue.localeCompare(bValue) : bValue.localeCompare(aValue);
      } else {
        return sortDirection === 'asc' ? aValue - bValue : bValue - aValue;
      }
    });
  }

  async function connectToBackend() {
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
        }        if (data.map) {
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
          
          // Update nodes with click heat data from pages
          if (data.pages && data.pages.length > 0) {
            const updatedNodes = graph.nodes.map(node => {
              const pageData = data.pages.find(p => p.url === node.id);
              if (pageData && pageData.click_positions) {
                const avgClickHeat = pageData.click_positions.length > 0 
                  ? pageData.click_positions.reduce((sum, click) => sum + (click.heat || 0), 0) / pageData.click_positions.length
                  : 0;
                return { ...node, click_heat: avgClickHeat };
              }
              return node;
            });
            graph = { ...graph, nodes: updatedNodes };
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
            alignment_score: data.sitewide_metrics.alignment || 0,
            click_heat: data.sitewide_metrics.click_heat || 0
          };
          console.log('Site metrics updated from data poll:', sitePalette);
        }

        if (data.heatmap_image) {
          heatmapImage = data.heatmap_image;
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
    }  }
  
  // Modernize sitemap by limiting nodes to max 6 children per parent
  function limitSitemapNodes(originalGraph) {
    if (!originalGraph || !originalGraph.nodes || !originalGraph.edges) {
      return originalGraph;
    }
    
    // Create a map of parent -> children relationships
    const parentChildMap = new Map();
    
    // Initialize all nodes as potential parents
    originalGraph.nodes.forEach(node => {
      parentChildMap.set(node.id, []);
    });
    
    // Build parent-child relationships from edges
    originalGraph.edges.forEach(edge => {
      const parentId = edge.source.id || edge.source;
      const childId = edge.target.id || edge.target;
      
      if (parentChildMap.has(parentId)) {
        parentChildMap.get(parentId).push(childId);
      }
    });
    
    // Limit each parent to max 6 children, keeping the highest scoring ones
    const keptNodes = new Set();
    const keptEdges = [];
    
    // Always keep all nodes that have no children or <= 6 children
    parentChildMap.forEach((children, parentId) => {
      keptNodes.add(parentId);
      
      if (children.length <= 6) {
        // Keep all children if <= 6
        children.forEach(childId => keptNodes.add(childId));
        // Keep all edges for this parent
        originalGraph.edges.forEach(edge => {
          const edgeParent = edge.source.id || edge.source;
          if (edgeParent === parentId) {
            keptEdges.push(edge);
          }
        });
      } else {
        // Limit to top 6 children based on score
        const childNodes = children
          .map(childId => originalGraph.nodes.find(n => n.id === childId))
          .filter(Boolean)
          .sort((a, b) => {
            const scoreA = (a.metrics?.color || 0) + (a.metrics?.neural || 0);
            const scoreB = (b.metrics?.color || 0) + (b.metrics?.neural || 0);
            return scoreB - scoreA;
          })
          .slice(0, 6);
        
        // Keep top 6 children
        childNodes.forEach(child => keptNodes.add(child.id));
        
        // Keep edges only to the top 6 children
        originalGraph.edges.forEach(edge => {
          const edgeParent = edge.source.id || edge.source;
          const edgeChild = edge.target.id || edge.target;
          if (edgeParent === parentId && childNodes.some(child => child.id === edgeChild)) {
            keptEdges.push(edge);
          }
        });
      }
    });
    
    // Filter nodes and edges based on what we're keeping
    const limitedNodes = originalGraph.nodes.filter(node => keptNodes.has(node.id));
    const limitedEdges = keptEdges;
    
    return {
      nodes: limitedNodes,
      edges: limitedEdges
    };
  }
  
  function renderNetwork() {
    if (!graphContainer || !graph || !graph.nodes || !graph.edges) return;
    
    // Clear previous graph
    while (graphContainer.firstChild) {
      graphContainer.removeChild(graphContainer.firstChild);
    }
    
    // Modernize sitemap by limiting child nodes per parent to max 6
    const limitedGraph = limitSitemapNodes(graph);
    
    // Prepare data for vis-network
    const nodes = limitedGraph.nodes.map(node => ({
      id: node.id,
      label: node.id.split('/').pop() || node.id,
      title: `${node.id}<br>Color: ${node.metrics?.color?.toFixed(1) || 0}/10<br>Font: ${node.metrics?.font?.toFixed(1) || 0}/10<br>Neural: ${node.metrics?.neural?.toFixed(1) || 0}/10<br>Alignment: ${node.metrics?.alignment?.toFixed(1) || 0}/10<br>Click Heat: ${node.click_heat?.toFixed(2) || 0}`,
      color: {
        background: node.color || '#f8fafc',
        border: '#cbd5e1',
        highlight: {
          background: '#e2e8f0',
          border: '#94a3b8'
        }
      },
      font: { size: 11, color: '#475569' },
      size: 14 + (node.metrics?.color ? node.metrics.color * 1.5 : 0)
    }));
    
    const edges = limitedGraph.edges.map(edge => ({
      from: edge.source.id || edge.source,
      to: edge.target.id || edge.target,
      arrows: 'to',
      width: 1.5,
      color: { color: '#cbd5e1', highlight: '#94a3b8', hover: '#94a3b8' },
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
        clickHeat: node.click_heat || 0,
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

  function toggleAccordion(section) {
    accordionState[section] = !accordionState[section];
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
{:else}  <!-- Main Application UI -->
  <div class="dashboard-container">
    <!-- Header Section -->
    <header class="main-header">
      <div class="header-content">
        <div class="logo">
          <h1>UI Analysis Dashboard</h1>
          <div class="status-indicator {status === 'Connected' ? (isAgentRunning ? 'active' : 'connected') : ''}"></div>
        </div>
        
        <div class="header-status">
          <span class="status-item">Status: <span class="status-value">{isAgentRunning ? 'Active' : 'Idle'}</span></span>
          <span class="status-item">Connection: <span class="status-value">{status}</span></span>
          {#if currentUrl}
            <span class="status-item">Current: <span class="status-value" title={currentUrl}>{currentUrl.split('/').pop() || currentUrl}</span></span>
          {/if}
        </div>
      </div>
    </header>
    
    <!-- Timeline Section -->
    <div class="timeline-section">
      <div class="timeline">
        {#if timelineEvents.length > 0}
          <div class="timeline-events">
            {#each timelineEvents as event}
              <div class="timeline-event">
                <div class="event-content">
                  <span class="event-time">{event.time}</span>
                  <span class="event-url">{event.url.split('/').slice(-1)[0] || event.url}</span>
                </div>
              </div>
            {/each}
          </div>
        {:else}
          <div class="timeline-empty">
            <span class="timeline-placeholder">Timeline will appear as the agent visits pages</span>
          </div>
        {/if}
      </div>
    </div><div class="main-content">
      <div class="left-panel">
        <!-- Screenshot Accordion Section -->        <div class="accordion-section">          <div class="accordion-header" class:expanded={accordionState.screenshot} on:click={() => toggleAccordion('screenshot')}>
            <h3>Current Page</h3>
            <span class="accordion-icon" class:expanded={accordionState.screenshot}>▼</span>
          </div>          {#if accordionState.screenshot}
            {#if screenshotUrl}
              <img src={screenshotUrl} alt="Current page screenshot" style="width: calc(100% - 2rem); margin: 1rem; border-radius: 8px; border: 1px solid #e0e0e0;" />
            {:else}
              <div class="placeholder">No screenshot available yet</div>
            {/if}
          {/if}
        </div>
          <!-- Color Palette Accordion Section -->        <div class="accordion-section">          <div class="accordion-header" class:expanded={accordionState.palette} on:click={() => toggleAccordion('palette')}>
            <h3>Color Palette</h3>
            <span class="accordion-icon" class:expanded={accordionState.palette}>▼</span>
          </div>          {#if accordionState.palette}
            {#if currentColorPalette && currentColorPalette.prominent_colors && currentColorPalette.prominent_colors.length > 0}
              <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; padding: 1rem; margin: 1rem;">
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
              </div>
            {:else}
              <div class="placeholder">No palette data available for current page ({currentUrl || 'N/A'})</div>
            {/if}
          {/if}
        </div>
          <!-- Fonts Accordion Section -->        <div class="accordion-section">          <div class="accordion-header" class:expanded={accordionState.fonts} on:click={() => toggleAccordion('fonts')}>
            <h3>Page Font Palette</h3>
            <span class="accordion-icon" class:expanded={accordionState.fonts}>▼</span>
          </div>          {#if accordionState.fonts}
            {#if currentFontGroups && Object.keys(currentFontGroups).length > 0}
              <div style="display: flex; flex-wrap: wrap; gap: 1rem; padding: 1rem; margin: 1rem;">
                {#each Object.entries(currentFontGroups) as [size, count]}
                  <div class="font-size-group">
                    <div class="font-size-sample" style="font-size: {Math.min(32, Math.max(10, parseInt(size)))}px">Aa</div>
                    <div class="font-size-info">{size}px ({count})</div>
                  </div>
                {/each}
              </div>
            {:else}
              <div class="placeholder">No font data available for current page ({currentUrl || 'N/A'})</div>
            {/if}
          {/if}
        </div>
          <!-- Sitemap Accordion Section -->        <div class="accordion-section">          <div class="accordion-header" class:expanded={accordionState.sitemap} on:click={() => toggleAccordion('sitemap')}>
            <h3>Site Map</h3>
            <span class="accordion-icon" class:expanded={accordionState.sitemap}>▼</span>
          </div>          {#if accordionState.sitemap}
            <div bind:this={graphContainer} style="border: 1px solid #e5e7eb; border-radius: 8px; background-color: #f9fafb; position: relative; height: 300px; overflow: hidden; margin: 1rem;"></div>
          {/if}
        </div>
          <!-- Heatmap Accordion Section -->
        <div class="accordion-section">          <div class="accordion-header" on:click={() => toggleAccordion('heatmap')}>
            <h3>Click Heatmap</h3>
            <span class="accordion-icon" class:expanded={accordionState.heatmap}>▼</span>
          </div>          {#if accordionState.heatmap}
            <div>
              {#if heatmapImage}
                <div class="heatmap-container-wrapper">
                  <img src={heatmapImage} alt="Click heatmap" class="heatmap-image" />
                  <div class="heatmap-legend">
                    <span class="legend-label">Cold</span>
                    <div class="legend-gradient"></div>
                    <span class="legend-label">Hot</span>
                  </div>
                </div>
              {:else}
                <div class="placeholder">No heatmap data available yet</div>
              {/if}
            </div>
          {/if}
        </div>
      </div>
      
      <div class="right-panel">
        <!-- Site-wide metrics -->
        <div class="site-metrics">
          <h3>Site-wide Metrics</h3>
            <div class="metrics-header">            <div>
              <p>Based on {graph?.nodes?.filter(n => n.metrics && n.timestamp && n.timestamp > 0)?.length || 0} analyzed pages</p>
            </div>
          </div>            <div class="metrics-cards">
              <!-- Neural Score -->
              <div class="metric-card neural-card">
                <h4>Neural Score</h4>
                <div class="big-score">
                  {sitePalette.neural_score?.toFixed(1) || 'N/A'}
                  <span class="out-of">/10</span>
                </div>
                <div class="score-bar neural-bar" style="width: {(sitePalette.neural_score || 0) * 10}%"></div>
              </div>
              
              <!-- Heatmap Score -->
              <div class="metric-card heatmap-card">
                <h4>Click Heat</h4>
                <div class="big-score">
                  {sitePalette.click_heat?.toFixed(2) || 'N/A'}
                  <span class="out-of">avg</span>
                </div>
                <div class="score-bar heatmap-bar" style="width: {Math.min((sitePalette.click_heat || 0) * 100, 100)}%"></div>
              </div>

              <!-- Color Quality -->
              <div class="metric-card color-card">
                <h4>Color Quality</h4>
                <div class="big-score">
                  {sitePalette.color_score?.toFixed(1) || 'N/A'}
                  <span class="out-of">/10</span>
                </div>
                <div class="score-bar color-bar" style="width: {(sitePalette.color_score || 0) * 10}%"></div>
              </div>
              
              <!-- Font Consistency -->
              <div class="metric-card font-card">
                <h4>Font Consistency</h4>
                <div class="big-score">
                  {(sitePalette.avg_font_consistency_score)?.toFixed(1) || 'N/A'} 
                  <span class="out-of">/10</span>
                </div>
                <div class="score-bar font-bar" style="width: {(sitePalette.avg_font_consistency_score || 0) * 10}%"></div>
              </div>
              
              <!-- Alignment Score -->
              <div class="metric-card alignment-card">
                <h4>Alignment Score</h4>
                <div class="big-score">
                  {sitePalette.alignment_score?.toFixed(1) || 'N/A'}
                  <span class="out-of">/10</span>
                </div>
                <div class="score-bar alignment-bar" style="width: {(sitePalette.alignment_score || 0) * 10}%"></div>
              </div>
            </div>
        </div>
        
        <!-- Color analysis table -->        <div class="color-table-section">
          <div class="table-header">
            <h3>Page Analysis</h3>
          </div>
          
          {#if graph && graph.nodes && graph.nodes.length > 0}
            <div class="table-container">
              <table class="color-table">                  <thead>
                  <tr>
                    <th class="sortable" on:click={() => sortTable('page')}>
                      Page
                      <span class="sort-indicator {sortField === 'page' ? 'active' : ''}">
                        {sortField === 'page' ? (sortDirection === 'asc' ? '↑' : '↓') : '↕'}
                      </span>
                    </th>
                    <th class="sortable" on:click={() => sortTable('neural')}>
                      Neural
                      <span class="sort-indicator {sortField === 'neural' ? 'active' : ''}">
                        {sortField === 'neural' ? (sortDirection === 'asc' ? '↑' : '↓') : '↕'}
                      </span>
                    </th>
                    <th class="sortable" on:click={() => sortTable('heat')}>
                      Heat
                      <span class="sort-indicator {sortField === 'heat' ? 'active' : ''}">
                        {sortField === 'heat' ? (sortDirection === 'asc' ? '↑' : '↓') : '↕'}
                      </span>
                    </th>
                    <th class="sortable" on:click={() => sortTable('color')}>
                      Color
                      <span class="sort-indicator {sortField === 'color' ? 'active' : ''}">
                        {sortField === 'color' ? (sortDirection === 'asc' ? '↑' : '↓') : '↕'}
                      </span>
                    </th>
                    <th class="sortable" on:click={() => sortTable('font')}>
                      Font
                      <span class="sort-indicator {sortField === 'font' ? 'active' : ''}">
                        {sortField === 'font' ? (sortDirection === 'asc' ? '↑' : '↓') : '↕'}
                      </span>
                    </th>
                    <th class="sortable" on:click={() => sortTable('alignment')}>
                      Alignment
                      <span class="sort-indicator {sortField === 'alignment' ? 'active' : ''}">
                        {sortField === 'alignment' ? (sortDirection === 'asc' ? '↑' : '↓') : '↕'}
                      </span>
                    </th>
                  </tr>
                </thead>                <tbody>
                  {#each getSortedNodes(graph.nodes.filter(n => n.metrics && n.timestamp && n.timestamp > 0)) as node}<tr 
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
                        {#if (node.metrics?.neural || 0) > 0}
                          <div class="score-pill neural-pill" 
                            style="background-color: {(node.metrics?.neural || 0) < 4 ? '#fee2e2' : 
                               (node.metrics?.neural || 0) < 7 ? '#fef3c7' : '#dcfce7'};
                               color: {(node.metrics?.neural || 0) < 4 ? '#dc2626' : 
                               (node.metrics?.neural || 0) < 7 ? '#d97706' : '#16a34a'};">
                            {node.metrics?.neural?.toFixed(1)}
                          </div>
                        {:else}
                          N/A
                        {/if}
                      </td>
                      <td class="score-cell">
                        {#if (node.click_heat || 0) > 0}
                          <div class="score-pill heat-pill" 
                            style="background-color: {(node.click_heat || 0) < 0.5 ? '#fee2e2' : 
                               (node.click_heat || 0) < 1.0 ? '#fef3c7' : '#dcfce7'};
                               color: {(node.click_heat || 0) < 0.5 ? '#dc2626' : 
                               (node.click_heat || 0) < 1.0 ? '#d97706' : '#16a34a'};">
                            {node.click_heat?.toFixed(2)}
                          </div>
                        {:else}
                          N/A
                        {/if}
                      </td>
                      <td class="score-cell">
                        {(node.metrics?.color || 0) > 0 ? node.metrics?.color?.toFixed(1) : 'N/A'}
                      </td>
                      <td class="score-cell">
                        {(node.metrics?.font || 0) > 0 ? node.metrics?.font?.toFixed(1) : 'N/A'}
                      </td>
                      <td class="score-cell">
                        {(node.metrics?.alignment || 0) > 0 ? node.metrics?.alignment?.toFixed(1) : 'N/A'}
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
  }  /* Custom Properties for Modern Design */
  :root {
    /* Core Colors */
    --color-primary-blue: #3b82f6;
    --color-secondary-blue: #1d4ed8;
    --color-light-blue: #dbeafe;
    --color-primary-orange: #f59e0b;
    --color-secondary-orange: #d97706;
    --color-light-orange: #fef3c7;

    /* Consolidated Neutrals - Only 4 shades */
    --color-white: #ffffff;
    --color-black: #0f1111;
    --color-gray-dark: #333333;      /* For primary text */
    --color-gray-medium: #6b7280;    /* For secondary text, icons */
    --color-gray-light: #e5e7eb;     /* For borders, dividers */
    --color-gray-lighter: #f1f3f5;   /* For backgrounds, hover states */    /* Core UI Colors */
    --color-primary: #3498db;
    --color-primary-hover: #2980b9;
    --color-primary-bg: #dbeafe;
    --color-primary-text: #1d4ed8;
    --color-error: #e74c3c;
    --color-error-bg: #fee2e2;
    --color-error-text: #dc2626;
    --color-success: #2ecc71;
    --color-success-bg: #dcfce7;
    --color-success-text: #16a34a;
    --color-secondary: #8b5cf6;

    /* Orange colors for heatmap */
    --color-orange-bg: #fef3c7;
    --color-orange-text: #d97706;

    /* Border and misc */
    --color-border: #d5d9d9;

    /* Metric Colors */
    --color-metric-green: #10b981;
    --color-metric-purple: #8b5cf6;
    --color-metric-red: #ef4444;

    /* Consolidated Shadows - Only 3 variants */
    --shadow-sm: 0 2px 4px rgba(0, 0, 0, 0.05);
    --shadow-md: 0 4px 8px rgba(0, 0, 0, 0.08);
    --shadow-lg: 0 10px 25px rgba(0, 0, 0, 0.15);    /* Special Purpose */
    --shadow-pulse-success: 0 0 5px rgba(46, 204, 113, 0.6);
    --shadow-button: rgba(213, 217, 217, .5) 0 2px 5px 0;
    --shadow-text: 0 0 1px rgba(0, 0, 0, 0.3);

    /* Overlays */
    --overlay-dark: rgba(0, 0, 0, 0.6);
    --overlay-light: rgba(255, 255, 255, 0.7);
    --overlay-border: rgba(0, 0, 0, 0.05);

    /* Radii & Transitions */
    --radius-xs: 4px;
    --radius-sm: 6px;
    --radius-md: 8px;
    --radius-lg: 12px;
    --transition-standard: all 0.2s ease;
  }  /* Base Styles and Reset */  
  :global(body) {
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
    background: var(--color-white);
    color: var(--color-gray-dark);
    line-height: 1.6;
    min-height: 100vh;
  }
  h1, h2, h3, h4 {
    margin: 0;
    font-weight: 600;
  }
  
  /* Modal Styles */  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: var(--overlay-dark);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1000;
    backdrop-filter: blur(3px);
  }
    .modal-container {
    background-color: var(--color-white);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-lg);
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
    color: var(--color-gray-dark);
  }
  
  .modal-container p {
    color: var(--color-gray-medium);
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
    border-radius: var(--radius-sm);
    border: 1px solid var(--color-gray-light);
    font-size: 1rem;
    resize: none;
    font-family: inherit;
    background-color: var(--color-gray-lighter);
    transition: border-color 0.2s;
  }
  
  .modal-content textarea:focus {
    outline: none;
    border-color: var(--color-primary);
    box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2);
  }
  .primary-button {
    background-color: var(--color-primary);
    color: var(--color-white);
    border: none;
    border-radius: var(--radius-sm);
    padding: 0.75rem;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: var(--transition-standard);
  }
  
  .primary-button:hover {
    background-color: var(--color-primary-hover);
  }
  
  .primary-button:active {
    transform: translateY(1px);
  }
  
  .primary-button:disabled {
    background-color: var(--color-gray-medium);
    cursor: not-allowed;
  }
    .error-message {
    color: var(--color-error);
    background-color: var(--color-error-bg);
    padding: 0.5rem;
    border-radius: var(--radius-sm);
    font-size: 0.9rem;
    border-left: 3px solid var(--color-error);
  }
  /* Dashboard Layout */  .dashboard-container {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
    background: var(--color-white);
  }

  .main-header {
    background-color: var(--color-white);
    border-bottom: 1px solid var(--color-gray-light);
    padding: 0.75rem 1rem;
  }
  
  .timeline-section {
    background-color: var(--color-white);
    border-bottom: 1px solid var(--color-gray-light);
    padding: 0.5rem 1rem;
  }
  
  .header-content {
    display: flex;
    justify-content: space-between;
    align-items: center;
    min-height: 3rem;
  }
  
  .logo {
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 1rem;
  }
  
  .header-status {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    font-size: 0.85rem;
  }
    .status-item {
    color: var(--color-gray-medium);
  }
  
  .status-value {
    color: var(--color-gray-dark);
    font-weight: 600;
  }
    .logo h1 {
    font-size: 1.25rem;
    color: var(--color-gray-dark);
    font-weight: 600;
    margin: 0;
  }    .status-indicator {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background-color: var(--color-error-text); /* Red for disconnected */
    transition: var(--transition-standard);
  }
  
  .status-indicator.connected {
    background-color: var(--color-primary-orange); /* Yellow for connected but not running */
  }
  
  .status-indicator.active {
    background-color: var(--color-success); /* Green for active/running */
    box-shadow: var(--shadow-pulse-success);
    animation: pulse 2s infinite;
  }
  
  @keyframes pulse {
    0% { box-shadow: 0 0 0 0 rgba(46, 204, 113, 0.6); }
    70% { box-shadow: 0 0 0 5px rgba(46, 204, 113, 0); }
    100% { box-shadow: 0 0 0 0 rgba(46, 204, 113, 0); }
  }  .timeline {
    background: transparent;
    border: none;
    border-radius: 0;
    overflow-x: auto;
    white-space: nowrap;
    padding: 0.5rem 0;
    scrollbar-width: none;
    -ms-overflow-style: none;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    min-height: 2.5rem;
    width: 100%;
  }
  
  .timeline::-webkit-scrollbar {
    display: none;
  }
    .timeline-events {
    display: flex;
    gap: 1rem;
    width: 100%;
    padding: 0 0.5rem;
  }
  .timeline-event {
    display: inline-flex;
    flex-direction: column;
    background-color: var(--color-white);
    border-radius: var(--radius-sm);
    padding: 1rem;
    min-width: 160px;
    border: 1px solid var(--color-gray-light);
    transition: var(--transition-standard);
    box-shadow: var(--shadow-sm);
    position: relative;
    overflow: hidden;
  }
  
  .timeline-event:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }
  
  .event-content {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
    .event-time {
    font-size: 0.75rem;
    color: var(--color-gray-medium);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
  }
  
  .event-url {
    font-weight: 700;
    font-size: 0.9rem;
    text-overflow: ellipsis;
    overflow: hidden;
    color: var(--color-gray-dark);
    white-space: nowrap;
  }  .timeline-empty {
    text-align: center;
    padding: 0.75rem 1rem;
    color: var(--color-gray-medium);
    font-style: italic;
    background-color: var(--color-white);
    border-radius: var(--radius-sm);
    border: 1px solid var(--color-gray-light);
    box-shadow: var(--shadow-sm);
    margin: 0 0.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 2rem;
  }
    .timeline-placeholder {
    font-size: 0.9rem;
    font-weight: 500;
  }
  
  .main-content {
    display: flex;
    flex-grow: 1;
    overflow: hidden;
  }  .left-panel {
    width: 33%;
    display: flex;
    flex-direction: column;
    border-right: 1px solid var(--color-gray-light);
    background-color: var(--color-white);
    overflow-y: auto;
    scrollbar-width: none;
    -ms-overflow-style: none;
  }
  
  .left-panel::-webkit-scrollbar {
    display: none;
  }
  
  .right-panel {
    width: 67%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background-color: var(--color-white);
  }  /* Screenshot container inside accordion */
    /* Right Panel Sections */
  .site-metrics {
    padding: 1.5rem;
    background-color: var(--color-white);
    border-bottom: 1px solid var(--color-border);
  }
  
  .site-metrics h3 {
    margin-bottom: 1rem;
    color: var(--color-gray-dark);
  }
  
  .metrics-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 1rem;
  }
  
  .metrics-header p {
    margin: 0;
    color: var(--color-gray-medium);
    font-size: 0.9rem;
  }
    .metrics-cards {
    display: flex;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }
    .metric-card {
    background-color: var(--color-white);
    border-radius: var(--radius-sm);
    padding: 1rem;
    flex: 1;
    box-shadow: var(--shadow-sm);
    position: relative;
    overflow: hidden;
    transition: var(--transition-standard);
    border: 1px solid var(--color-gray-light);
  }
  
  .metric-card:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }
  
  .metric-card h4 {
    font-size: 0.8rem;
    margin-bottom: 0.5rem;
    color: var(--color-gray-medium);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 600;
  }
  
  .big-score {
    font-size: 1.8rem;
    font-weight: bold;
    color: var(--color-gray-dark);
    margin-bottom: 0.5rem;
    transition: var(--transition-standard);
  }
    /* Unique colors for each metric */
  .neural-card .big-score {
    color: var(--color-primary);
  }
  
  .heatmap-card .big-score {
    color: var(--color-primary-orange);
  }
  
  .color-card .big-score {
    color: var(--color-success);
  }
  
  .font-card .big-score {
    color: var(--color-secondary);
  }
  
  .alignment-card .big-score {
    color: var(--color-error);
  }
  /* Pill styling for neural and heatmap scores */
  .neural-pill {
    background-color: var(--color-primary-bg);
    color: var(--color-primary-text);
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    display: inline-block;
    border: none;
    text-shadow: none;
    box-shadow: none;
  }
    .out-of {
    font-size: 0.9rem;
    color: var(--color-gray-medium);
    font-weight: normal;
  }
    .score-bar {
    height: 4px;
    border-radius: 2px;
    transition: width 0.5s ease-out;
  }
  
  /* Unique bar colors */
  .neural-bar {
    background-color: var(--color-primary);
  }
  
  .heatmap-bar {
    background-color: var(--color-primary-orange);
  }
  
  .color-bar {
    background-color: var(--color-success);
  }
  
  .font-bar {
    background-color: var(--color-secondary);
  }
  
  .alignment-bar {
    background-color: var(--color-error);
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
    .table-container {
    background-color: var(--color-white);
    border-radius: var(--radius-sm);
    box-shadow: var(--shadow-sm);
    overflow: hidden;
    margin-bottom: 1.5rem;
  }
  
  .color-table {
    width: 100%;
    border-collapse: collapse;
  }  .color-table th {
    padding: 0.75rem;
    text-align: left;
    color: var(--color-gray-medium);
    border-bottom: 1px solid var(--color-border);
    font-weight: 600;
    user-select: none;
    cursor: pointer;
    position: relative;
    transition: var(--transition-standard);
  }
  
  .color-table th:hover {
    background-color: var(--color-gray-lighter);
  }
  
  .color-table th.sortable {
    padding-right: 2rem;
  }
    .sort-indicator {
    position: absolute;
    right: 0.5rem;
    top: 50%;
    transform: translateY(-50%);
    font-size: 0.75rem;
    color: var(--color-gray-medium);
    opacity: 0.5;
    transition: var(--transition-standard);
  }
  
  .sort-indicator.active {
    opacity: 1;
    color: var(--color-primary);
  }
  
  .color-table td {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--color-gray-lighter);
    font-size: 0.9rem;
  }
  .color-table tr:hover {
    background-color: var(--color-gray-lighter);
    cursor: pointer;
  }
  
  .color-table tr {
    transition: var(--transition-standard);
  }
  
  .color-table tr:hover {
    transform: translateY(-1px);
    box-shadow: var(--shadow-sm);
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
  }.score-pill {
    display: inline-block;
    padding: 0.2rem 0.5rem;
    border-radius: 20px;
    color: var(--color-white);
    font-weight: bold;
    font-size: 0.8rem;
    text-shadow: var(--shadow-text);
    text-align: center;
    min-width: 28px;
    background-color: var(--color-gray-medium);
    box-shadow: var(--shadow-sm);
  }
  .color-block {
    height: 42px;
    flex: 1;
    min-width: 80px;
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    box-shadow: var(--shadow-sm);
    transition: var(--transition-standard);
    border: 2px solid var(--overlay-light);
    outline: 1px solid var(--overlay-border);
  }
  
  .color-block:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }/* Visualization styles for accordion content */
  
  .font-size-group {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 65px;
    padding: 0.75rem 0.5rem;
    background-color: var(--color-white);
    border-radius: var(--radius-sm);
    box-shadow: var(--shadow-sm);
    transition: var(--transition-standard);
    border: 1px solid var(--overlay-border);
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
    background: var(--color-gray-medium);
  }
  
  .font-size-group:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }
  
  .font-size-sample {
    margin-bottom: 0.3rem;
  }
  
  .font-size-info {
    font-size: 0.7rem;
    color: var(--color-gray-medium);  }/* Heatmap Accordion Styles */

  .heatmap-container-wrapper {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 100%;
    max-width: 800px;
    margin: 0 auto;
  }

  .heatmap-image {
    width: 70%;
    object-fit: contain;
    border-radius: var(--radius-sm);
    box-shadow: var(--shadow-sm);
    border: 2px solid var(--color-white);
    transform: scaleY(-1); /* Fix for upside-down heatmap */
    background-color: var(--color-white);
  }

  .heatmap-legend {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-top: 1rem;
    padding: 0.75rem 1.5rem;
    background-color: var(--color-white);
    border-radius: 25px;
    box-shadow: var(--shadow-sm);
    font-size: 0.9rem;
    border: 1px solid var(--color-border);
  }  .legend-gradient {
    width: 80px;
    height: 14px;
    border-radius: var(--radius-sm);
    background: linear-gradient(to right, var(--color-primary), var(--color-primary-orange), var(--color-error));
    border: 1px solid var(--color-border);
  }

  .legend-label {
    color: var(--color-gray-dark);
    font-weight: 600;
    font-size: 0.85rem;
  }

  .placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 200px;
    color: var(--color-gray-medium);
    font-style: italic;
  }
  /* Left Panel Accordion Styles */
  .accordion-section {
    background-color: var(--color-white);
  }
  
  .accordion-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    cursor: pointer;
    background-color: var(--color-gray-lighter);
    transition: var(--transition-standard);
    user-select: none;
    border-top: 1px solid var(--color-gray-light);
    border-bottom: 0px;
  }
  .accordion-header.expanded {
    border-bottom: 1px solid var(--color-gray-light);
  }
  
  .accordion-header:hover {
    background-color: var(--color-gray-light);
  }
  
  .accordion-header h3 {
    margin: 0;
    color: var(--color-gray-dark);
    font-weight: 600;
    font-size: 1rem;
  }
  
  .accordion-icon {
    transition: var(--transition-standard);
    color: var(--color-gray-medium);
    font-size: 0.8rem;
  }
  
  .accordion-icon.expanded {
    transform: rotate(180deg);
  }
  /* Placeholder text styling */
  .placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--color-gray-medium);
    font-style: italic;
    font-size: 0.9rem;
    text-align: center;
    min-height: 120px;
    padding: 1rem;
    width: 100%;
  }
  
  .placeholder.centered {
    min-height: 200px;
  }

</style>
