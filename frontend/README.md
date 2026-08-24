# Frontend (React)

Not yet scaffolded. Next step:

```bash
npm create vite@latest . -- --template react-ts
npm install
```

## Planned structure
- `src/hooks/useConversationSocket.ts` -- WebSocket client connecting to
  `ws://localhost:8000/ws/conversation/{conversation_id}`
- `src/components/FlashCard.tsx` -- renders each incoming flash card
- `src/components/ConversationPanel.tsx` -- live transcript view for the rep
- `src/components/DistributorProfile.tsx` -- sidebar showing the current
  distributor's structured profile fields

Keep this thin: the frontend's job is to render what the backend pushes
over the WebSocket, not to hold business logic.
