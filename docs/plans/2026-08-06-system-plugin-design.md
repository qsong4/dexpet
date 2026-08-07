# System Control Plugin Design

**Goal:** macOS system helpers via LLM tools + always-on-top toggle for the pet.

## Tools

- open_app / open_url / open_path (whitelisted)
- clipboard_get / clipboard_set
- volume_get / volume_set
- set_dnd / lock_screen / trigger_shortcut (whitelist)
- set_always_on_top — persist + push to desktop via WS

## Safety

No arbitrary shell. App/path/shortcut allowlists. User-home path restriction.
