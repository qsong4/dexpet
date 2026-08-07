# Custom Sprite + Desktop Wander Design

**Goal:** 按情绪上传宠物图片；桌宠在屏幕上踱步并偶尔长距离走动。

## Sprite

- Storage: `~/Library/Application Support/DexPet/sprites/{emotion}.png`
- Emotions: idle, happy, curious, thinking, speaking, sad, surprised
- Settings UI: upload / clear / preview per slot
- Desktop: load custom pixmap when present; else painted cat
- Hot-reload via `/config` poll or WS emotion + settings save response

## Wander

- Desktop `PetWindow` state machine: idle → pace → walk → idle
- Pace: small offset every 3–8s; walk: random point every 45–90s with easing
- Pause on hover-chat, drag, pinned reminder; right-click toggle
