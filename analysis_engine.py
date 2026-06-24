"""
解析エンジン(バッティング/ピッチング 共通の計算ロジック)

このファイルは画面(UI)を持ちません。「動画を渡したら数値が返ってくる」
計算部分だけを切り出しています。今はターミナルから直接動かして、
正しい数値が出るかだけ確認します(画面に組み込むのは次回以降)。

事前準備:
    pip install mediapipe opencv-python numpy

使い方(ターミナルで):
    python analysis_engine.py 動画ファイルのパス batting 右打者
    python analysis_engine.py 動画ファイルのパス pitching 右投げ
"""

import os
import sys
import urllib.request

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

# =============================================================================
# モデル設定
# =============================================================================
MODEL_FILENAME = "pose_landmarker_full.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_full/float16/latest/pose_landmarker_full.task"
)

# BlazePose 33点のうち、今回使うインデックス
NOSE = 0
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_ELBOW, RIGHT_ELBOW = 13, 14
LEFT_WRIST, RIGHT_WRIST = 15, 16
LEFT_HIP, RIGHT_HIP = 23, 24
LEFT_KNEE, RIGHT_KNEE = 25, 26
LEFT_ANKLE, RIGHT_ANKLE = 27, 28


def load_landmarker():
    if not os.path.exists(MODEL_FILENAME):
        print("モデルをダウンロード中...(初回だけ)")
        urllib.request.urlretrieve(MODEL_URL, MODEL_FILENAME)

    base_options = mp_python.BaseOptions(model_asset_path=MODEL_FILENAME)
    options = mp_vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=mp_vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return mp_vision.PoseLandmarker.create_from_options(options)


# =============================================================================
# 幾何計算ヘルパー
# =============================================================================
def xy(landmarks, idx, w, h):
    lm = landmarks[idx]
    return np.array([lm.x * w, lm.y * h])


def joint_angle(a, b, c):
    """3点 a-b-c で、点bにおける角度(度)"""
    ba = a - b
    bc = c - b
    denom = (np.linalg.norm(ba) * np.linalg.norm(bc)) + 1e-9
    cos_angle = np.clip(np.dot(ba, bc) / denom, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_angle)))


def line_angle(p1, p2):
    """p1→p2 を結ぶ線の、水平線に対する角度(度)"""
    return float(np.degrees(np.arctan2(p2[1] - p1[1], p2[0] - p1[0])))


def trunk_tilt_from_vertical(mid_hip, mid_shoulder):
    """上体(腰→肩)が、真上方向からどれだけ傾いているか(度)。0度=直立"""
    trunk = mid_shoulder - mid_hip
    vertical = np.array([0.0, -1.0])  # 画像座標では上方向はyが減る向き
    denom = (np.linalg.norm(trunk) * np.linalg.norm(vertical)) + 1e-9
    cos_angle = np.clip(np.dot(trunk, vertical) / denom, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_angle)))


# =============================================================================
# 動画からランドマークの時系列を取り出す(共通処理)
# =============================================================================
def extract_landmark_series(video_path: str, landmarker):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"動画を開けませんでした: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    frames = []  # 各フレームのランドマーク(検出できなければNone)
    frame_idx = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp_ms = int((frame_idx / fps) * 1000)
        result = landmarker.detect_for_video(mp_image, timestamp_ms)

        frames.append(result.pose_landmarks[0] if result.pose_landmarks else None)
        frame_idx += 1

    cap.release()

    detected = sum(1 for f in frames if f is not None)
    if detected == 0:
        raise ValueError(
            "動画から人を検出できませんでした。映りが小さい/暗い/横向きでない、"
            "などが原因の可能性があります。"
        )
    if detected / len(frames) < 0.5:
        print(
            f"⚠️ 警告: 全{len(frames)}フレーム中、検出できたのは{detected}フレームだけです。"
            "結果の信頼性が低いかもしれません。"
        )

    return frames, fps, width, height


# =============================================================================
# バッティング解析(5項目)
# =============================================================================
def analyze_batting(video_path: str, batter_side: str) -> dict:
    """batter_side: '右打者' または '左打者'"""
    landmarker = load_landmarker()
    frames, fps, w, h = extract_landmark_series(video_path, landmarker)

    lead = "L" if batter_side == "右打者" else "R"  # リード側(投手側)の腕

    hip_x_list, wrist_speed_list = [], []
    ankle_dist_list, body_height_list = [], []
    lead_elbow_angle_list, sep_angle_list = [], []

    prev_mid_wrist = None

    for lm in frames:
        if lm is None:
            hip_x_list.append(np.nan)
            wrist_speed_list.append(np.nan)
            ankle_dist_list.append(np.nan)
            body_height_list.append(np.nan)
            lead_elbow_angle_list.append(np.nan)
            sep_angle_list.append(np.nan)
            prev_mid_wrist = None
            continue

        l_sh, r_sh = xy(lm, LEFT_SHOULDER, w, h), xy(lm, RIGHT_SHOULDER, w, h)
        l_el, r_el = xy(lm, LEFT_ELBOW, w, h), xy(lm, RIGHT_ELBOW, w, h)
        l_wr, r_wr = xy(lm, LEFT_WRIST, w, h), xy(lm, RIGHT_WRIST, w, h)
        l_hip, r_hip = xy(lm, LEFT_HIP, w, h), xy(lm, RIGHT_HIP, w, h)
        l_an, r_an = xy(lm, LEFT_ANKLE, w, h), xy(lm, RIGHT_ANKLE, w, h)
        nose = xy(lm, NOSE, w, h)

        mid_hip = (l_hip + r_hip) / 2
        mid_wrist = (l_wr + r_wr) / 2
        mid_ankle = (l_an + r_an) / 2

        hip_x_list.append(mid_hip[0])
        ankle_dist_list.append(np.linalg.norm(l_an - r_an))
        body_height_list.append(np.linalg.norm(nose - mid_ankle))
        sep_angle_list.append(line_angle(l_sh, r_sh) - line_angle(l_hip, r_hip))

        if lead == "L":
            lead_elbow_angle_list.append(joint_angle(l_sh, l_el, l_wr))
        else:
            lead_elbow_angle_list.append(joint_angle(r_sh, r_el, r_wr))

        if prev_mid_wrist is not None:
            wrist_speed_list.append(np.linalg.norm(mid_wrist - prev_mid_wrist) * fps)
        else:
            wrist_speed_list.append(np.nan)
        prev_mid_wrist = mid_wrist

    hip_x = np.array(hip_x_list)
    wrist_speed = np.array(wrist_speed_list)
    ankle_dist = np.array(ankle_dist_list)
    body_height = np.array(body_height_list)
    lead_elbow_angle = np.array(lead_elbow_angle_list)
    sep_angle = np.array(sep_angle_list)

    body_height_ref = np.nanmedian(body_height)

    # インパクトの瞬間 ≒ 手首スピードが最大になったフレーム、で近似する
    impact_idx = int(np.nanargmax(wrist_speed))
    # 着地(ステップ)の瞬間 ≒ 両足の間隔が最大になったフレーム、で近似する
    footplant_idx = int(np.nanargmax(ankle_dist))

    return {
        "体重移動量(身長比)": float((np.nanmax(hip_x) - np.nanmin(hip_x)) / body_height_ref),
        "腰肩捻れ最大角度(度)": float(np.nanmax(np.abs(sep_angle))),
        "インパクト時リード肘角度(度)": float(lead_elbow_angle[impact_idx]),
        "手首最大スピード(身長/秒)": float(np.nanmax(wrist_speed) / body_height_ref),
        "ステップ幅(身長比)": float(ankle_dist[footplant_idx] / body_height_ref),
    }


# =============================================================================
# ピッチング解析(5項目)
# =============================================================================
def analyze_pitching(video_path: str, pitcher_arm: str) -> dict:
    """pitcher_arm: '右投げ' または '左投げ'"""
    landmarker = load_landmarker()
    frames, fps, w, h = extract_landmark_series(video_path, landmarker)

    throw = "R" if pitcher_arm == "右投げ" else "L"  # 投げる側
    land = "L" if throw == "R" else "R"              # 着地する前足側(投げる側と反対)

    ankle_dist_list, body_height_list = [], []
    sep_angle_list, elbow_height_list = [], []
    knee_angle_land_list, trunk_tilt_list = [], []
    throw_wrist_speed_list = []

    prev_throw_wrist = None

    for lm in frames:
        if lm is None:
            ankle_dist_list.append(np.nan)
            body_height_list.append(np.nan)
            sep_angle_list.append(np.nan)
            elbow_height_list.append(np.nan)
            knee_angle_land_list.append(np.nan)
            trunk_tilt_list.append(np.nan)
            throw_wrist_speed_list.append(np.nan)
            prev_throw_wrist = None
            continue

        l_sh, r_sh = xy(lm, LEFT_SHOULDER, w, h), xy(lm, RIGHT_SHOULDER, w, h)
        l_el, r_el = xy(lm, LEFT_ELBOW, w, h), xy(lm, RIGHT_ELBOW, w, h)
        l_wr, r_wr = xy(lm, LEFT_WRIST, w, h), xy(lm, RIGHT_WRIST, w, h)
        l_hip, r_hip = xy(lm, LEFT_HIP, w, h), xy(lm, RIGHT_HIP, w, h)
        l_kn, r_kn = xy(lm, LEFT_KNEE, w, h), xy(lm, RIGHT_KNEE, w, h)
        l_an, r_an = xy(lm, LEFT_ANKLE, w, h), xy(lm, RIGHT_ANKLE, w, h)
        nose = xy(lm, NOSE, w, h)

        mid_hip = (l_hip + r_hip) / 2
        mid_shoulder = (l_sh + r_sh) / 2
        mid_ankle = (l_an + r_an) / 2

        ankle_dist_list.append(np.linalg.norm(l_an - r_an))
        body_height_list.append(np.linalg.norm(nose - mid_ankle))
        sep_angle_list.append(line_angle(l_sh, r_sh) - line_angle(l_hip, r_hip))
        trunk_tilt_list.append(trunk_tilt_from_vertical(mid_hip, mid_shoulder))

        if throw == "R":
            throw_shoulder, throw_elbow, throw_wrist = r_sh, r_el, r_wr
        else:
            throw_shoulder, throw_elbow, throw_wrist = l_sh, l_el, l_wr
        elbow_height_list.append(throw_shoulder[1] - throw_elbow[1])  # +なら肘が肩より上

        if land == "L":
            knee_angle_land_list.append(joint_angle(l_hip, l_kn, l_an))
        else:
            knee_angle_land_list.append(joint_angle(r_hip, r_kn, r_an))

        if prev_throw_wrist is not None:
            throw_wrist_speed_list.append(np.linalg.norm(throw_wrist - prev_throw_wrist) * fps)
        else:
            throw_wrist_speed_list.append(np.nan)
        prev_throw_wrist = throw_wrist

    ankle_dist = np.array(ankle_dist_list)
    body_height = np.array(body_height_list)
    sep_angle = np.array(sep_angle_list)
    elbow_height = np.array(elbow_height_list)
    knee_angle_land = np.array(knee_angle_land_list)
    trunk_tilt = np.array(trunk_tilt_list)
    throw_wrist_speed = np.array(throw_wrist_speed_list)

    body_height_ref = np.nanmedian(body_height)

    # 着地の瞬間 ≒ 両足の間隔が最大になったフレーム、で近似する
    footplant_idx = int(np.nanargmax(ankle_dist))
    # リリースの瞬間 ≒ 投げる側の手首スピードが最大になったフレーム、で近似する
    release_idx = int(np.nanargmax(throw_wrist_speed))

    return {
        "ステップ幅(身長比)": float(ankle_dist[footplant_idx] / body_height_ref),
        "着地時腰肩捻れ角度(度)": float(sep_angle[footplant_idx]),
        "着地時肘高さ(身長比)": float(elbow_height[footplant_idx] / body_height_ref),
        "リリース時上体前傾角度(度)": float(trunk_tilt[release_idx]),
        "着地脚膝角度(度)": float(knee_angle_land[footplant_idx]),
    }


# =============================================================================
# ターミナルから直接テストできるようにする
# =============================================================================
if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("使い方:")
        print("  python analysis_engine.py 動画のパス batting 右打者")
        print("  python analysis_engine.py 動画のパス pitching 右投げ")
        sys.exit(1)

    video_path, mode, side = sys.argv[1], sys.argv[2], sys.argv[3]

    if mode == "batting":
        result = analyze_batting(video_path, side)
    elif mode == "pitching":
        result = analyze_pitching(video_path, side)
    else:
        print("2番目の引数は batting か pitching にしてください")
        sys.exit(1)

    print("\n=== 解析結果 ===")
    for key, value in result.items():
        print(f"{key}: {value:.3f}")
