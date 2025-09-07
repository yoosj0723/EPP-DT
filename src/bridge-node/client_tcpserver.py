import os
import time
import socket
import threading
from opcua import Client

class BatchBallReader:
    def __init__(self,
                 endpoint="opc.tcp://localhost:4840",
                 host="0.0.0.0", port=9002,  # ← 포트는 안전하게 9001 추천
                 interval=0.5):
        # OPC UA 서버 연결
        self.client = Client(endpoint)
        self.client.connect()
        print("▶ OPC UA 서버에 연결됨")

        # 네임스페이스 인덱스 가져오기
        self.idx = self.client.get_namespace_index("http://example.com/balls")
        print(f"▶ 네임스페이스 인덱스: {self.idx}")

        # BallGroup 노드 탐색
        root = self.client.get_root_node()
        objects = root.get_child(["0:Objects"])
        ball_group = objects.get_child([f"{self.idx}:BallGroup"])
        print("▶ BallGroup 노드를 찾았습니다")

        # BallGroup 하위 Ball 노드 및 변수 캐시
        balls = ball_group.get_children()
        print(f"▶ BallGroup 하위 Ball 개수: {len(balls)}")
        self.ball_names = []
        self.node_list = []
        for ball in balls:
            name = ball.get_browse_name().Name
            self.ball_names.append(name)

            var_map = {var.get_browse_name().Name: var for var in ball.get_children()}
            self.node_list.extend([
                var_map['id'],
                var_map['X'],
                var_map['Y'],
                var_map['color']
            ])

        # TCP 서버 생성
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        print(f"▶ TCP 서버 대기 중: {self.host}:{self.port}")

        # 주기
        self.interval = interval

    def _send_batch(self, batch_msg: str):
        payload = batch_msg.encode("utf-8")
        length = len(payload)
        length_bytes = length.to_bytes(4, byteorder='big')

        with self.conn_lock:
            try:
                print(f"[DEBUG] Sending batch of size {length} bytes")
                print(f"[DEBUG] Batch content:\n{batch_msg}")
                self.conn.sendall(length_bytes)
                self.conn.sendall(payload)
                print(f"[DEBUG] Payload sent (Length={length})")
            except Exception as e:
                print(f"[Error] 클라이언트 전송 실패: {e}")

    def run(self):
        print("▶ 클라이언트 접속 대기 중...")
        self.conn, addr = self.server_socket.accept()
        print(f"✅ 클라이언트 연결됨: {addr}")
        self.conn_lock = threading.Lock()

        print(f"▶ Reader 시작: {len(self.ball_names)}개 Ball, 주기={self.interval}s")

        try:
            while True:
                start = time.perf_counter()

                try:
                    values = self.client.get_values(self.node_list)
                    print(f"[DEBUG] Ball values being read:")
                    batch_msg_lines = []

                    for i, name in enumerate(self.ball_names):
                        base = i * 4
                        ball_id, x, y, color = values[base:base+4]
                        print(f"  {name}: id={ball_id}, x={x}, y={y}, color={color}")

                        # 무조건 모든 값 전송
                        line = f"{name}, id:{ball_id}, X:{x:.2f}, Y:{y:.2f}, color:{color}"
                        batch_msg_lines.append(line)

                    batch_msg = "\n".join(batch_msg_lines) + "\n"
                    self._send_batch(batch_msg)

                except TimeoutError:
                    print("[Warning] OPC UA get_values Timeout 발생 → Skip")
                    continue
                except Exception as e:
                    print(f"[Error] OPC UA get_values Exception 발생: {e}")
                    continue

                elapsed = time.perf_counter() - start
                if elapsed < self.interval:
                    time.sleep(self.interval - elapsed)
                else:
                    print(f"[Warning] 읽기+조립 시간이 {elapsed:.3f}s로 주기({self.interval}s)를 넘어섰습니다.")

        except KeyboardInterrupt:
            print("■ Reader 중단 (KeyboardInterrupt)")

        finally:
            self.conn.close()
            self.server_socket.close()
            self.client.disconnect()
            print("■ TCP 서버 종료 및 OPC UA 연결 해제 완료")

if __name__ == "__main__":
    reader = BatchBallReader()
    reader.run()
