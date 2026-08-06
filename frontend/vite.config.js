import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Builds to frontend/dist, which FastAPI mounts at the root (ADR-0001). One
// origin, so the app calls /api/hardware with no host and no CORS.
export default defineConfig({
  plugins: [vue()],
})
