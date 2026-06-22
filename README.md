```text
 █████╗ ███████╗ ██████╗██╗██╗     ██╗███╗   ██╗███████╗  ██
██╔══██╗██╔════╝██╔════╝██║██║     ██║████╗  ██║██╔════╝  █████
███████║███████╗██║     ██║██║     ██║██╔██╗ ██║█████╗    ████████
██╔══██║╚════██║██║     ██║██║     ██║██║╚██╗██║██╔══╝    ████████
██║  ██║███████║╚██████╗██║███████╗██║██║ ╚████║███████╗  █████
╚═╝  ╚═╝╚══════╝ ╚═════╝╚═╝╚══════╝╚═╝╚═╝  ╚═══╝╚══════╝  ██

```

**ASCILINE** is a high-performance, cross-platform real-time ASCII video rendering engine. **Our core objective is to transform the web into a highly dynamic and interactive typographic canvas.** By mapping pixels to text-based representations, we unlock new possibilities for web media delivery.

| Output | Details |
| :--- | :--- |
| <img src="https://github.com/user-attachments/assets/ccc727c9-c697-49f2-85e1-6f8c366f2019" width="400" alt="Original Source" /> | **Original Source**<br>Standard MP4 video file. |
| <img src="https://github.com/user-attachments/assets/6bd7f5c0-81de-49fe-ba0d-9a8872ec8ae3" width="400" alt="ASCII Mode" /> | **ASCII Mode**<br>Showcases rendered using Mode 3 (32K Colors) from a 30fps source. |
| <img src="https://github.com/user-attachments/assets/1fd88c3d-97d1-441a-a071-16de24ea82c0" width="400" alt="PIXEL Mode" /> | **PIXEL Mode**<br>Showcases rendered using Mode 5 (16m Colors) combined with the `--pixel` flag for ultra-high fidelity. |

## 🎯 Strategic Vision & Core Capabilities

1. **Pure Typographic Manipulation**: The visual stream is not a standard media file—it's raw HTML/Canvas text. This makes the impossible possible: you can apply real-time CSS filters (neon glows, text shadows, animations) to video content.
2. **Local AI & LLM Ready**: By reducing complex pixel streams into structured logical strings, ASCILINE acts as a perfect bridge for AI. Instead of feeding heavy computer vision models, lightweight LLMs can process semantic video summaries.
3. **Ultra-Low Bandwidth & Zero GPU (valid for ASCII MOD)**: Standard codecs (H.264/VP9) require dedicated hardware decoders, choking microcontrollers and weak devices. ASCILINE offloads the heavy lifting to the backend, streaming only lightweight text frames. By scaling down the output quality (using fewer columns), extremely low bandwidth requirements can be achieved. This means you can play fluid, real-time video on devices with constrained networks and zero GPU capabilities (smart appliances, retro terminals, basic microcontrollers).
4. **🌐 Works Everywhere**: No `<video>`  tags. No browser-side decoding. 
No autoplay restrictions. To the browser, it's just text on a canvas.

## 🚀 Technical Features

-   **Cross-Platform**: Runs seamlessly on Windows, macOS, and Linux.
-   **Real-Time ASCII Streaming**: Low-latency video-to-ASCII conversion.
-   **Real-Time Pixel Streaming**: Replaces characters with colored blocks, approaching 360p video quality.
-   **High Performance**: Uses **HTML5 Canvas** for rendering, optimized for cinematic 24-30 FPS playback. High-FPS sources are automatically decimated for stability.
-   **Master Clock Sync**: The audio track acts as the absolute master clock, guaranteeing perfect A/V synchronization.
-   **Low-Overhead Binary Protocol**: Frames are streamed as raw binary (`Uint8Array`) directly to the canvas, saving bandwidth and CPU.
-   **Multiple Color Modes**: Supports everything from classic B&W to 16M color ultra-fidelity.
-   **Flexible Video Management**: Supports JSON playlists (per-video mode & volume), 
      folder-based auto-queuing (filesystem order), single-file mode, and infinite loop 
      playback — all controlled via CLI arguments.

## 🛠️ Architecture

1.  **Backend (Python/FastAPI)**: Decodes video using OpenCV, maps pixels to ASCII characters via NumPy, and streams binary data.
2.  **Frontend (Vanilla JS)**: Receives binary frames via WebSockets, manages a jitter buffer, and renders to a Canvas grid.
3.  **Communication**: Optimized WebSocket protocol with a custom `INIT` handshake for dynamic resolution/FPS adjustment.

## 🗜️ Adaptive Frame Codec (opt-in,valid for ASCI mod [2-5])

The original binary protocol re-sends the full grid every frame. An opt-in
adaptive codec picks the smallest of three encodings per frame and tags it in a
1-byte header — **without changing the rendered output**:

| tag | encoding | best for |
| :-- | :------- | :------- |
| `0` RAW | framebuffer as-is (legacy) | incompressible frames |
| `1` ZLIB | `zlib(framebuffer)` | general motion |
| `2` DELTA | only the cells that changed since the last frame | static / low-motion |

Clients opt in with `/ws?codec=adaptive`; omit it and you get the **original
protocol byte-for-byte**, so existing clients are unaffected. A keyframe is
forced periodically so dropped packets / late joiners resync. The decoder
(`codec.js`) is shared by the browser and the test suite, so the shipped path is
the tested one.

**Measured wire savings** (mode 5, 200×80 grid):

| content | vs. legacy |
| :------ | :--------- |
| static screen / slideshow | **0.3%** (≈375×) |
| high-motion / full-frame change | 63% (never worse than legacy) |

An optional `--quality {lossless,high,balanced,low}` enables lossy *temporal
delta*: a colour cell is only re-sent once it drifts past a tolerance from what
the viewer already sees (the character plane stays exact), cutting the hard
cases a further ~15–30% at imperceptible quality. Default is `lossless`
(bit-exact).

**Monitor Bandwidth in Real-Time:**
You can append the `--debug` flag when launching the server to see live bandwidth comparisons (RAW vs WIRE bytes) and the exact compression ratio in your terminal. This is highly useful for measuring the real-time savings of the adaptive codec on your specific video sources.

> Verified two independent ways, both **bit-exact**: Python-encoded vectors
> decoded by `codec.js` in Node (`experiments/gen_vectors.py` →
> `experiments/check_vectors.js`), and a live `adaptive`-vs-`legacy` WebSocket
> diff (`experiments/test_e2e.js`). Generate the test clips with
> `experiments/make_test_clips.sh`. (A fuller mutation-test + Autobahn

**LAN / Network Streaming:**
To stream the video on your local network (Wi-Fi), use the `--host` flag:
> python stream_server.py video.mp4 --host 0.0.0.0

## 📦 Installation

### 1. Clone the repository
```bash
git clone https://github.com/YusufB5/ASCILINE.git
cd ASCILINE
```

### 2. Install dependencies
```bash
pip install fastapi uvicorn opencv-python numpy websockets
```

**Optional — play from YouTube (and other yt-dlp sites):**
```bash
pip install yt-dlp
```
Only needed if you pass a URL instead of a local file. Local playback works
without it. URL playback also uses FFmpeg (see below) to normalize downloads.
### 🔈 Audio Support (FFmpeg Required)
To enable server-side audio processing (Volume 1-5), you must have FFmpeg installed.

**Option 1: Package Manager (Recommended)**
- **Windows:** `winget install ffmpeg`
- **macOS:** `brew install ffmpeg`
- **Linux:** `sudo apt install ffmpeg`

**Option 2: Manual Installation (Windows)**
If you get a `FileNotFoundError` or don't want to modify system variables:
1. Download [FFmpeg ZIP](https://github.com/BtbN/FFmpeg-Builds/releases/latest).
2. Extract `ffmpeg.exe` from the `bin` folder.
3. Drop it directly into your `ASCILINE` project folder alongside `stream_server.py`.
### 3. Run the Web Server

**Single video:**
```bash
python stream_server.py video.mp4 --cols 240
```

**YouTube / URL (requires `yt-dlp`):** pass any yt-dlp-supported URL in place of a file.
```bash
python stream_server.py "https://youtu.be/VIDEO_ID" --cols 240
python stream_server.py "https://www.youtube.com/playlist?list=..." --cols 220 --loop
```
A single video is downloaded (≤480p — ASCILINE only needs a tiny grid) and cached
in `videos/` by id, so replays are instant. A playlist/channel URL expands into one
queue entry per video, each fetched on demand as it plays. A `playlist.json` may
also list URLs; those are fetched lazily too, so the server starts immediately
instead of downloading the whole list up front. Every download is normalized to a
standard H.264/AAC/constant-frame-rate mp4 so playback and audio stay reliable
regardless of the source codec.

**Folder mode — drop your videos into `videos/` and run:**
```bash
python stream_server.py --folder videos --cols 200
python stream_server.py --folder videos --cols 230 --loop          # infinite loop
python stream_server.py --folder videos --mode 5 --pixel --cols 320 --vol 2  # all videos same settings
```
Videos play in **filesystem order** (top to bottom as they appear in the folder, not alphabetically). Just add/remove files from the `videos/` folder to control the queue.

**JSON Playlist — full control per video:**
```bash
python stream_server.py --playlist playlist.json --cols 220
python stream_server.py --playlist playlist.json --cols 220 --loop
```
Use `playlist.json` when you need different `--mode` or `--vol` settings for each video.


Open `http://localhost:8000` in your browser.

### Player Controls

Hover previews are built once per video on first hover, in a single ffmpeg pass,
and kept in memory — nothing written to disk. Disable with `--no-thumbnails`.
To use a prebuilt sprite instead, point the `/scrub` route at it.

### 4. Run directly in Terminal (Standalone)
If you prefer to bypass the web interface, you can render the video directly inside an ANSI-supported terminal (zero-flicker, true color):
```bash
python ascii_video_player2.py video.mp4 --cols 100 --quality 0
```

> ⚠️ **Note:** Do not resize your terminal window during playback, as dynamic text wrapping will corrupt the ASCII layout.

## 🎨 Customization

You can easily customize the look and feel of the engine:

### Styling
Edit `style.css` to change the accent colors and typography using CSS variables:
```css
:root {
    --accent-color: #00ff41; /* Classic Matrix Green */
    --bg-color: #050505;
}
```

### Rendering Modes
The engine supports different fidelity levels via the `--mode` flag:
- `1`: Black & White (DOM mode)
- `2`: 512 Colors
- `3`: 32K Colors
- `4`: 262K Colors
- `5`: 16M Colors (Ultra)

```bash
python stream_server.py --mode 5 --cols 240 --rows 100
```
### 📐 Resolution & Auto-Scaling
By default, you only need to specify the width (`--cols`). ASCILINE will automatically calculate the correct `--rows` based on the source video's aspect ratio to prevent stretching.

- **ASCII Mode Recommended:** `--cols 200` to `--cols 240` (Best balance of text detail and cinematic 30 FPS performance).
- **Pixel Mode Recommended:** `--cols 600` to `--cols 900` (Provides near-HD visual quality. Performance heavily depends on your machine's CPU/VRAM).
- > **Smart Defaults:** If you do not specify a `--cols` value, ASCILINE automatically defaults to `450` when Pixel Mode is enabled, and `200` for standard ASCII text mode. 
- > ⚠️ **Hardware Limits & A/V Sync:** If you push the `--cols` too high for your specific hardware (e.g., `1350` on a laptop vs a gaming desktop), the Python backend won't be able to encode and send the massive frames fast enough. When the video stream lags behind the audio, you will experience A/V desync (audio finishing early). If this happens, simply lower your `--cols` value!
```bash
python stream_server.py video.mp4 --mode 5 --cols 240
# Terminal will show: [AUTO] 1920x1080 → grid 240x67
```
### Server-Side Volume Control
Volume is controlled at the server level via the `--vol` flag (scale 0–5).
When set to `0`, the audio engine (FFmpeg) **never runs**, saving CPU and bandwidth.

| `--vol` | FFmpeg Multiplier | Description |
|---------|------------------|-------------|
| `0`     | —                | Muted (no processing) |
| `1`     | 1.0×             | Normal (default) |
| `3`     | 1.5×             | Loud |
| `5`     | 2.0×             | Double volume |

```bash
python stream_server.py video.mp4 --pixel --cols 560 --vol 0   # Silent
python stream_server.py video.mp4 --cols 220 --vol 3   # Loud
```

### Playlist Format (`playlist.json`)
Each entry can override the global `--mode`, `--pixel`, `--vol`, and `--cols` defaults:
```json
[
    { "video": "intro.mp4",  "mode": 1, "vol": 1 },
    { "video": "main.mp4",   "mode": 5, "pixel": true, "vol": 3, "cols": 520 },
    { "video": "outro.mp4",  "mode": 3, "vol": 2, "cols": 240 }
]
```
Video paths are resolved automatically — the engine checks the project root and the `videos/` subfolder, so you can write just the filename.


### 🟢 Live Interactive Showcase
Experience the ASCILINE engine running live directly in your browser with multiple rendering modes. 👉 **[Try it out at asciline.dev](https://www.asciline.dev)**


## 📈 Star History
[![Star History Chart](https://api.star-history.com/svg?repos=YusufB5/ASCILINE&type=Date)](https://star-history.com/#YusufB5/ASCILINE&Date)

### ☕ Support the Project ❤️ 
If you find this project helpful, you can support me by donating crypto:
* **Solana (SOL / USDC):** `H1wSQAhjgsu7AxenF4e5ZBYiBjkhDLVzkKaZuVPcrE14`
* **Ethereum (ETH / USDT):** `0x85B2f970045c0F7c282089Ab6CF897C20230e086`
* **Bitcoin (BTC):** `bc1qvtcl55v54gkzwnp2zxn70usea3gf5ncncqa0fv`

## 📜 License & Ethical Guardrails

ASCILINE is distributed under the MIT License, but with an anti ad strict ethical guardrail. 

See the [LICENSE](LICENSE) file for the full text, which includes the **ANTI-ADVERTISEMENT RESTRICTION** clause.

## 📬 Contact & Questions
[asciline.engine@gmail.com](mailto:asciline.engine@gmail.com)
