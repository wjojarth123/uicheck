import networkx as nx
import matplotlib.pyplot as plt
import matplotlib
import threading
import time
from typing import Dict, Any
import os

# Use Agg backend for non-GUI environments
matplotlib.use('Agg')

class ExplorationVisualizer:
    """Real-time visualization of the agent exploration tree"""
    def __init__(self, update_interval=5.0):
        """
        Initialize the visualizer
        
        Args:
            update_interval: Time between visualization updates in seconds
        """
        self.graph = nx.DiGraph()
        self.lock = threading.Lock()
        self.update_interval = update_interval
        self.running = False
        self.visualization_thread = None
        self.agent_data = {}
        self.output_file = "exploration_tree.png"
    def start(self):
        """Start the visualization thread"""
        self.running = True
        self.visualization_thread = threading.Thread(target=self._visualization_loop)
        self.visualization_thread.daemon = True
        self.visualization_thread.start()
        
    def stop(self):
        """Stop the visualization thread"""
        self.running = False
        if self.visualization_thread:
            self.visualization_thread.join(timeout=2.0)
    
    def update_agent(self, agent_id: str, data: Dict[str, Any]):
        """
        Update the agent data in the visualization
        
        Args:
            agent_id: The unique identifier for the agent
            data: Dictionary containing agent data including:
                  - url: Current URL
                  - parent_id: ID of the parent agent (if any)
                  - depth: Exploration depth
                  - status: Agent status (active, closed, etc.)
        """
        with self.lock:
            # Add or update the node
            self.agent_data[agent_id] = data
            
            # Add node to graph
            label = f"{data.get('depth', '?')}: {self._truncate_url(data.get('url', 'unknown'))}"
            self.graph.add_node(agent_id, label=label)
            
            # Add edge if there's a parent
            parent_id = data.get('parent_id')
            if parent_id:
                self.graph.add_edge(parent_id, agent_id)
    
    def remove_agent(self, agent_id: str):
        """
        Mark an agent as closed in the visualization
        
        Args:
            agent_id: The unique identifier for the agent
        """
        with self.lock:
            if agent_id in self.agent_data:
                self.agent_data[agent_id]['status'] = 'closed'
    
    def _visualization_loop(self):
        """Main loop for updating the visualization"""
        while self.running:
            try:
                self._update_visualization()
            except Exception as e:
                print(f"Error updating visualization: {e}")
            time.sleep(self.update_interval)
        
        # Final update before stopping
        try:
            self._update_visualization()
        except Exception as e:
            print(f"Error in final visualization update: {e}")
    
    def _update_visualization(self):
        """Update the visualization with the current state"""
        with self.lock:
            if not self.graph.nodes:
                return
                
            plt.figure(figsize=(12, 8))
            
            # Create a simple spring layout instead of using graphviz
            pos = nx.spring_layout(self.graph, seed=42)
            
            # Create node colors based on status
            node_colors = []
            for node in self.graph.nodes:
                status = self.agent_data.get(node, {}).get('status', 'unknown')
                if status == 'active':
                    node_colors.append('lightgreen')
                elif status == 'closed':
                    node_colors.append('lightgray')
                else:
                    node_colors.append('lightblue')
            
            # Draw the graph
            nx.draw(
                self.graph, 
                pos, 
                with_labels=True,
                node_color=node_colors,
                node_size=1500,
                font_size=8,
                arrows=True,
                labels={node: self.graph.nodes[node]['label'] for node in self.graph.nodes}
            )
            
            plt.title(f"Web Exploration Tree - {len(self.graph.nodes)} Agents")
            
            try:
                # Ensure the directory exists
                directory = os.path.dirname(self.output_file)
                if directory and not os.path.exists(directory):
                    os.makedirs(directory, exist_ok=True)
                    
                plt.savefig(self.output_file, dpi=100, bbox_inches='tight')
            except Exception as e:
                print(f"Error saving visualization: {e}")
            
            plt.close()
    
    def _truncate_url(self, url, max_length=30):
        """Truncate URL for display purposes"""
        if not url or len(url) <= max_length:
            return url
        
        return url[:max_length-3] + "..."
    
    def save_final_visualization(self, filename=None):
        """Save the final visualization to a file"""
        if filename:
            self.output_file = filename
            
        # Ensure the directory exists
        directory = os.path.dirname(self.output_file)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
            
        try:
            self._update_visualization()
            print(f"Final visualization saved to {self.output_file}")
        except Exception as e:
            print(f"Error saving final visualization: {e}")

# Example usage:
if __name__ == "__main__":
    # Test the visualizer
    visualizer = ExplorationVisualizer(update_interval=1.0)
    visualizer.start()
    
    # Add some test agents
    visualizer.update_agent("root", {
        "url": "https://example.com", 
        "parent_id": None, 
        "depth": 0,
        "status": "active"
    })
    
    time.sleep(1)
    
    for i in range(3):
        visualizer.update_agent(f"child{i}", {
            "url": f"https://example.com/page{i}", 
            "parent_id": "root", 
            "depth": 1,
            "status": "active"
        })
    
    time.sleep(1)
    
    for i in range(2):
        visualizer.update_agent(f"grandchild{i}", {
            "url": f"https://example.com/page0/subpage{i}", 
            "parent_id": "child0", 
            "depth": 2,
            "status": "active"
        })
    
    time.sleep(1)
    visualizer.remove_agent("child1")
    
    time.sleep(3)
    visualizer.stop()
    visualizer.save_final_visualization("test_visualization.png") 