"""
Webcam Diagnostic & Test Utility
Quickly tests and lists all working webcam indices and backend options.
"""

import platform
import cv2


def test_cameras():
    print("========================================")
    print("   WEBCAM DIAGNOSTIC & TEST UTILITY     ")
    print(f"   OS: {platform.system()} ({platform.release()})")
    print("========================================")

    is_windows = platform.system() == "Windows"
    backends = [
        ("DirectShow (CAP_DSHOW)", cv2.CAP_DSHOW),
        ("Default (CAP_ANY)", cv2.CAP_ANY),
    ] if is_windows else [
        ("V4L2 (CAP_V4L2)", cv2.CAP_V4L2),
        ("Default (CAP_ANY)", cv2.CAP_ANY),
    ]

    working_cameras = []

    for index in range(4):
        print(f"\nChecking Camera Index [{index}]...")
        for name, backend in backends:
            try:
                cap = cv2.VideoCapture(index, backend)
                if cap and cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None and frame.size > 0:
                        h, w = frame.shape[:2]
                        print(f"  [SUCCESS] Camera {index} opened with {name} -> Resolution: {w}x{h}")
                        working_cameras.append((index, name, w, h))
                        cap.release()
                        break
                    cap.release()
                else:
                    if cap:
                        cap.release()
            except Exception as e:
                print(f"  [ERROR] Camera {index} with {name}: {e}")

    print("\n----------------------------------------")
    if working_cameras:
        print(f"Found {len(working_cameras)} working camera(s):")
        for idx, backend, w, h in working_cameras:
            print(f"  -> Index {idx}: {w}x{h} ({backend})")
        print("\nTo launch AI Safety Guard with a specific camera index:")
        print(f"  python main.py --mock-hardware --source {working_cameras[0][0]}")
    else:
        print("[WARN] No working camera found. Check camera permissions in Windows Settings.")
    print("----------------------------------------\n")


if __name__ == "__main__":
    test_cameras()
