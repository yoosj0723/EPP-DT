using System;
using System.Net.Sockets;
using System.Text;
using UnityEngine;
using System.Linq;
using System.Collections.Generic;

public class BallBatchTCPReceiver : MonoBehaviour
{
    public string serverIP = "127.0.0.1";
    public int port = 9003;
    TcpClient client;
    NetworkStream stream;
    private List<byte> buffer = new List<byte>();

    public GameObject[] ballObjects;
    public int imageWidth = 1280;
    public int imageHeight = 720;
    public float unityWidth = 10f;
    public float unityHeight = 5f;

    void Start()
    {
        try
        {
            client = new TcpClient(serverIP, port);
            stream = client.GetStream();
            Debug.Log($"[TCP] 연결 성공: {serverIP}:{port}");
        }
        catch (Exception e)
        {
            Debug.LogError($"[TCP] 연결 실패: {e.Message}");
        }
    }

    public Vector3 ConvertPixelToUnity(int x_pixel, int y_pixel)
    {
        float unityX = -((x_pixel / (float)imageWidth) * unityWidth - (unityWidth / 2f));
        float unityZ = ((imageHeight - y_pixel) / (float)imageHeight) * unityHeight - (unityHeight / 2f);
        return new Vector3(unityX, 0, unityZ);
    }

    void Update()
    {
        if (client == null || !client.Connected || stream == null) return;
        if (!stream.DataAvailable) return;

        // 1. 네트워크에서 온 모든 데이터를 임시 버퍼에 누적
        byte[] tmp = new byte[1024];
        while (stream.DataAvailable)
        {
            int n = stream.Read(tmp, 0, tmp.Length);
            if (n <= 0) break;
            buffer.AddRange(tmp.Take(n));
        }

        // 2. 완전한 패킷(4바이트 길이 + payload)만큼 쌓였을 때만 처리
        while (buffer.Count >= 4)
        {
            // (1) 길이 파싱
            byte[] lengthBytes = buffer.Take(4).ToArray();
            int dataLength = BitConverter.ToInt32(lengthBytes.Reverse().ToArray(), 0);

            // (2) 방어 코드: 이상값
            if (dataLength <= 0 || dataLength > 100000)
            {
                Debug.LogWarning($"[TCP] 데이터 길이 값 이상: {dataLength}");
                buffer.RemoveRange(0, 4);
                continue;
            }

            // (3) payload가 다 도착했는지 확인
            if (buffer.Count < 4 + dataLength) break;

            // (4) payload 추출
            byte[] payload = buffer.Skip(4).Take(dataLength).ToArray();
            buffer.RemoveRange(0, 4 + dataLength);

            // (5) 해석
            string msg = Encoding.UTF8.GetString(payload);
            Debug.Log($"[TCP] 수신: \n{msg}");

            string[] lines = msg.Split(new[] { "\r\n", "\n" }, StringSplitOptions.RemoveEmptyEntries);
            foreach (string line in lines)
            {
                try
                {
                    string[] parts = line.Split(',');
                    if (parts.Length < 5) continue;
                    int id = int.Parse(parts[1].Split(':')[1]);
                    int x_pixel = (int)float.Parse(parts[2].Split(':')[1]);
                    int y_pixel = (int)float.Parse(parts[3].Split(':')[1]);
                    string color = parts[4].Split(':')[1].Trim().ToLower();

                    if (id >= 0 && id < ballObjects.Length && ballObjects[id] != null)
                    {
                        Vector3 unityPos = ConvertPixelToUnity(x_pixel, y_pixel);
                        ballObjects[id].transform.position = unityPos;
                    }
                }
                catch (Exception ex)
                {
                    Debug.LogWarning("[파싱 실패] " + line + " (" + ex.Message + ")");
                }
            }
        }
    }

    void OnApplicationQuit()
    {
        try
        {
            stream?.Close();
            client?.Close();
        }
        catch { }
    }
}