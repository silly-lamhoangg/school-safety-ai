# Changelog

## 1.0

- Fixed FFmpeg discovery so an unavailable encoder no longer prevents the AI
  engine from starting; evidence videos retain their original encoding if
  conversion is unavailable.
- Made the AI monitor thread join during shutdown to prevent interpreter exit
  while the thread is still writing to the console.
- Upgraded person detection and tracking from YOLO11n to YOLO26n.
- Added Windows setup instructions and excluded local databases, secrets,
  model weights, and captured media from Git.
