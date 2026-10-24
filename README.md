Project: Blind Echo (First-Person Horror Prototype)
Status: Early Development / Playable Prototype
Engine: Python (Ursina Engine)

Project Overview:
This is a playable prototype for a blind first-person horror game. The core loop revolves around audio cues, echolocation, and maze navigation. The player relies on directional sound and visual wireframe pulses to survive.

Implemented Mechanics:

Procedural Maze: 40x40 DFS-generated labyrinth.

Echolocation System: Right-click sends a ground wave and expanding wireframe sphere, highlighting colliders.

Movement & Noise: Run (Shift), Walk (WASD), Sneak (Left-click). Different states emit different noise radii.

Enemy AI: State machine (Patrol, Chase, Search) reacting to noise events. Proximity triggers UI Vignette (red edges) and dynamic audio (heartbeat).

Lives & Progress: 3 lives. Respawn preserves collected fuse count.

🚧 Limitations & Disclaimer:

This is NOT a finished product.

Placeholder Assets: The game currently uses basic primitive shapes (cubes, spheres, wireframes) because external .obj models (like the monster) and .mp3/.wav audio files are currently missing or not bundled. The code has fallback mechanisms, but the full atmospheric experience relies on the user adding their own assets.

Level 2: The UI selection exists, but the level itself is completely empty/unimplemented.

Bugs: Collision clipping issues (seeing through walls when close) are being actively debugged.

