import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		proxy: {
			// Proxy API requests to Flask backend
			'/api': {
				target: 'http://localhost:5000',
				changeOrigin: true,
				secure: false
			}
		}
	}
});
