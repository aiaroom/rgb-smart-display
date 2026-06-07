import cv2

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/video", tags=["video"])

def generate_frames():
    cap = cv2.VideoCapture("rtsp://host.docker.internal:8554/live")

    if not cap.isOpened():
        print("Camera not opened")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    try:
        while True:
            success, frame = cap.read()

            if not success or frame is None:
                print("Failed to read frame")
                break

            ret, buffer = cv2.imencode(".jpg", frame)

            if not ret:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + buffer.tobytes()
                + b"\r\n"
            )
    finally:
        cap.release()


@router.get("/feed")
async def video_feed():
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )