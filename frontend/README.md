# SecureFlow Dashboard — React Frontend

Professional security assessment dashboard built with React, TypeScript, Tailwind CSS, and Vite.

## Tech Stack

- **Vite** — Lightning-fast build tool
- **React 18** — UI framework
- **TypeScript** — Type safety
- **Tailwind CSS** — Utility-first styling
- **Lucide React** — Professional icons
- **Recharts** — Data visualization (ready to use)

## Development

### Prerequisites

```bash
node --version  # Should be v18+
npm --version   # Should be v9+
```

### Setup

```bash
cd frontend
npm install
```

### Development Server

```bash
npm run dev
```

The dashboard will be available at `http://localhost:3000` with proxy to backend at `http://localhost:5000`.

### Build for Production

```bash
npm run build
```

This builds the React app to `../secureflow/static/dist/` which is served by the FastMCP server.

## Architecture

### Directory Structure

```
src/
├── components/          # React components
│   ├── Dashboard.tsx    # Main dashboard
│   ├── AgentMessages.tsx # Chat-like agent messages
│   ├── LogViewer.tsx    # Live log streaming
│   ├── ProgressPhases.tsx # Phase progress with timers
│   ├── ProviderStatus.tsx # LLM provider status
│   ├── Badge.tsx        # Reusable badge component
│   ├── SettingsModal.tsx # Provider configuration
│   └── ScanHistory.tsx   # Scan history modal
├── hooks/               # Custom React hooks
│   ├── useSSE.ts        # Server-Sent Events connection
│   └── useAPI.ts        # API data fetching
├── types/               # TypeScript types
├── styles/              # Global CSS
├── App.tsx              # Root component
└── main.tsx             # Entry point
```

### Key Components

#### Dashboard
- Real-time SSE connection to `/stream/{target}`
- Agent message streaming
- Live log viewer
- Phase progress tracking
- Provider status display
- Settings and history modals

#### AgentMessages
- Displays agent-agent collaboration
- Color-coded by agent role
- Auto-scrolling to latest message
- Timestamp for each message

#### LogViewer
- Severity-colored log entries (INFO/WARNING/ERROR/SUCCESS)
- Fixed-height scrollable area
- Timestamps on each log
- Terminal-like styling

#### ProgressPhases
- Visual progress through 3 phases
- Individual timers (MM:SS format)
- Animated running state
- Completion checkmarks

#### ProviderStatus
- Shows Claude, Gemini, Ollama health
- Test buttons for each provider
- Real-time availability status
- Provider priority display

## API Integration

### SSE Stream

The dashboard connects to `/stream/{target}` for real-time updates:

```javascript
new EventSource(`/stream/${target}`)
```

Events:
- `start` — Scan initiated
- `phase_complete` — Phase finished
- `complete` — Assessment done
- `error` — Error occurred

### REST Endpoints

- `GET /api/history` — Get scan history

## Styling

### Color System

Using CSS variables (dark theme by default):

```css
--background: 8 12% 5%;
--foreground: 0 0% 95%;
--primary: 217 91% 60%;
--success: 142 71% 45%;
--destructive: 0 84% 60%;
```

Defined in `src/styles/globals.css` and configured in `tailwind.config.js`.

### Tailwind Configuration

- Dark mode using CSS variables
- Extended colors (success, warning, etc.)
- Custom animations (pulse, slideIn)
- Responsive grid layout

## Deployment

### For Production

1. Build the React app:
   ```bash
   npm run build
   ```

2. The FastMCP server automatically serves from `static/dist/`

3. Dashboard available at `http://localhost:5000/ui`

### For Development

Run both in parallel:

```bash
# Terminal 1: React dev server
cd frontend && npm run dev

# Terminal 2: Python server
python -m secureflow server
```

Access at `http://localhost:3000` (proxies to backend).

## Performance

- **Vite** provides instant HMR (hot module reload)
- **Tailwind** tree-shakes unused CSS
- **React** uses memo for expensive components
- **Log viewer** handles 1000+ logs efficiently

## Future Enhancements

- [ ] Live data visualization (recharts integration)
- [ ] Virtualized log list (for 10k+ logs)
- [ ] WebSocket instead of SSE (bi-directional)
- [ ] Dark/light theme toggle
- [ ] Custom dashboard layouts
- [ ] Report viewer embedded in dashboard
- [ ] Export logs to CSV

## Troubleshooting

### Build fails

```bash
rm -rf node_modules package-lock.json
npm install
npm run build
```

### CORS issues in dev

The Vite config has proxy rules for `/stream` and `/api` endpoints.

### TypeScript errors

```bash
npx tsc --noEmit
```

## Contributing

- Follow React hooks best practices
- Use TypeScript for all new code
- Add types to `src/types/index.ts`
- Test in both dev and production builds
