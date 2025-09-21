from ultralytics import YOLO
import cv2
from opcua import Server, ua
import time


def create_ball_node(idx, parent, i):
    name = f"Ball{i}"
    ball = parent.add_object(idx, name)
    id_var = ball.add_variable(idx, "id", i, ua.VariantType.Int32)
    x_var = ball.add_variable(idx, "X", 0.0, ua.VariantType.Float)
    y_var = ball.add_variable(idx, "Y", 0.0, ua.VariantType.Float)
    color_var = ball.add_variable(idx, "color", "none", ua.VariantType.String)
    for v in (id_var, x_var, y_var, color_var):
        v.set_writable()
    return ball, id_var, x_var, y_var, color_var


class BallServer:
    def __init__(self, max_ball=10):
        self.server = Server()
        self.server.set_endpoint("opc.tcp://0.0.0.0:4840")
        self.server.set_server_name("BallTrackingServer")
        uri = "http://example.com/balls"
        self.idx = self.server.register_namespace(uri)
        objects_node = self.server.get_objects_node()
        self.group = objects_node.add_object(self.idx, "BallGroup")
        self.ball_nodes = {}
        for i in range(max_ball):
            ball, id_var, x_var, y_var, color_var = create_ball_node(self.idx, self.group, i)
            name = ball.get_browse_name().Name
            self.ball_nodes[name] = {
                'id_var': id_var,
                'x': x_var,
                'y': y_var,
                'color': color_var
            }

    def start(self):
        self.server.start()
        print("OPC UA Server started")

    def set_ball_position(self, id: int, x: float, y: float, color: str = "none"):
        name = f"Ball{id}"
        if name in self.ball_nodes:
            vars = self.ball_nodes[name]
            vars['id_var'].set_value(id)
            vars['x'].set_value(x)
            vars['y'].set_value(y)
            vars['color'].set_value(color)
        else:
            print(f"[Error] {name} not found")

    def stop(self):
        self.server.stop()
        print("OPC UA Server stopped")


# YOLO 모델 로드
model = YOLO(r"C:\Users\momndad\Desktop\산종설\best.pt")
class_names = model.names

# 클래스별 색상맵 (텍스트용) 및 BGR 맵핑 (드로잉용)
class_to_color = {
    "red_ball": "red",
    "green_ball": "green",
    "blue_ball": "blue",
}
color_bgr = {
    "red": (0, 0, 255),
    "green": (0, 255, 0),
    "blue": (255, 0, 0),
    "unknown": (255, 255, 255)
}

# OPC UA 서버 구동
MAX_ID = 6
bs = BallServer(max_ball=MAX_ID)
bs.start()

active_ids = {}      # {raw_id: assigned_id}
id_last_seen = {}    # {assigned_id: frame_idx}


def assign_id(raw_id, frame_idx):
    if raw_id in active_ids:
        assigned = active_ids[raw_id]
        id_last_seen[assigned] = frame_idx
        return assigned
    used = set(active_ids.values())
    for i in range(MAX_ID):
        if i not in used:
            active_ids[raw_id] = i
            id_last_seen[i] = frame_idx
            return i
    oldest_id = min(id_last_seen, key=id_last_seen.get)
    for k, v in list(active_ids.items()):
        if v == oldest_id:
            del active_ids[k]
    active_ids[raw_id] = oldest_id
    id_last_seen[oldest_id] = frame_idx
    return oldest_id

# 웹캠 설정
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("웹캠 로드 실패")
    bs.stop()
    exit()

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

cv2.namedWindow("YOLOv8 + OPC UA", cv2.WINDOW_NORMAL)
cv2.resizeWindow("YOLOv8 + OPC UA", 1280, 720)

frame_idx = 0
while True:
    ret, frame = cap.read()
    if not ret:
        break

    results = model.track(
        source=frame,
        persist=True,
        stream=False,
        conf=0.15,
        iou=0.5,
        tracker=r"C:\Users\momndad\Desktop\산종설\custom_botsort.yaml"
    )
    r = results[0]
    boxes = r.boxes
    annotated = r.orig_img.copy()

    assigned_this_frame = set()
    this_frame_ids = set()
    frame_objects = []

    if boxes is not None and boxes.id is not None:
        ids = boxes.id.int().tolist()
        classes = boxes.cls.int().tolist()
        xyxy = boxes.xyxy.tolist()

        for i in range(len(ids)):
            raw_id     = ids[i]
            class_id   = classes[i]
            class_name = class_names[class_id]
            x1, y1, x2, y2 = map(int, xyxy[i])
            x_center = int((x1 + x2) / 2)
            y_center = int((y1 + y2) / 2)

            assigned_id = assign_id(raw_id, frame_idx)
            if assigned_id in assigned_this_frame:
                continue
            assigned_this_frame.add(assigned_id)
            this_frame_ids.add(assigned_id)

            # 색상 이름 및 BGR 설정
            color_name = class_to_color.get(class_name, "unknown")
            box_color = color_bgr.get(color_name, (255,255,255))
            frame_objects.append((assigned_id, x_center, y_center, color_name))

            # 바운딩 박스와 ID만 출력
            label = f"ID:{assigned_id}"
            cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2)
            cv2.putText(annotated, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 2)

    # OPC UA 서버 업데이트
    for obj_id, x, y, color in frame_objects:
        bs.set_ball_position(obj_id, x, y, color=color)

    # 안 보이는 slot 초기화
    for i in range(MAX_ID):
        if i not in this_frame_ids:
            bs.set_ball_position(i, 0, 0, color="none")

    cv2.imshow("YOLOv8 + OPC UA", annotated)
    if cv2.waitKey(1) & 0xFF == 27:
        break

    frame_idx += 1

cap.release()
cv2.destroyAllWindows()
bs.stop()
print("OPC UA 종료 및 추적 완료")