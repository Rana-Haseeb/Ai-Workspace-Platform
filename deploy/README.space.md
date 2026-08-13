---
title: AI Workspace
emoji: 🔗
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Multi-user AI workspaces with cited answers and persistent memory
---

<!-- Only needed if you deploy to Hugging Face Spaces, which requires a PRO plan for the Docker
     SDK. The free path is Render — see docs/DEPLOYMENT.md. Kept because the config is correct
     and costs nothing to keep. -->

# AI Workspace

A multi-user AI workspace where every answer can be traced — to a document page, or to something
you said three sessions ago.

Upload documents and the assistant answers from them, citing the exact page it used. Tell it a
preference once and it still knows next week, in a new session. Every workspace is isolated;
every message records its own token count, latency and cost.

**Source and full documentation:** see the project repository.

## Trying it

1. Create an account — any email works, nothing is sent anywhere.
2. Make a workspace.
3. Upload a PDF, Word file or Markdown document, then ask a question about it. The answer
   carries numbered source chips; click one to see the exact excerpt the model was given.
4. Tell it something about yourself, then start a **new** conversation and ask about it.

## Notes

- Data lives in a managed Postgres database, so accounts and conversations survive restarts.
  **Uploaded files do not** — the container filesystem is ephemeral, so a restart keeps the
  document's text and citations but loses the original file.
- The model providers are free tiers. If a daily quota runs out, retrieval degrades to keyword
  search and says so rather than quietly returning worse answers.
