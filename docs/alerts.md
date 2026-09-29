# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert 1

- Tên: `high_tail_latency`
- Severity: critical
- Duration: 5m
- Kênh thông báo: Slack `#day13-l3a-oncall`
- SLI/SLO liên quan: `primary_slo.fast_successful_requests` trong `config/slo.yaml` (good event: `latency_ms <= 3000`, target 99.5%/28 ngày).
- Điều kiện và thời gian duy trì: `latency_p95_ms > 3000` liên tục trong 5 phút (panel `latency` trong `config/dashboard.yaml`, đúng threshold `p95 lte 3000`).
- Ảnh hưởng tới người dùng: request `/chat` trả lời chậm hơn ngưỡng SLO, trải nghiệm chờ lâu, có nguy cơ timeout ở client.
- Ba bước kiểm tra đầu tiên:
  1. Mở panel `latency` để xác nhận P95/P99 và TTFT tăng từ thời điểm nào.
  2. Lọc `data/logs.jsonl` trong khoảng thời gian đó theo `latency_ms` cao, lấy `correlation_id` của các request chậm nhất.
  3. Mở trace Langfuse có cùng `correlation_id`, xem span `retrieve-context` hay `generate-response` chiếm phần lớn thời gian.
- Mitigation tạm thời: nếu span `retrieve-context` là nguyên nhân (ví dụ do incident `rag_slow`), tắt incident bằng `python scripts/inject_incident.py --scenario rag_slow --disable` hoặc failover sang fallback doc tĩnh; nếu do generation, giảm tải bằng cách hạ concurrency của load test/khách hàng.
- Owner: on-call-engineer

## Alert 2

- Tên: `elevated_error_rate`
- Severity: warning
- Duration: 5m
- Kênh thông báo: Slack `#day13-l3a-oncall`
- SLI/SLO liên quan: guardrail `error_rate_pct_max: 2` trong `config/slo.yaml`.
- Điều kiện và thời gian duy trì: `error_rate_pct > 2` liên tục trong 5 phút (panel `errors`, threshold `error_rate_pct lte 2`).
- Ảnh hưởng tới người dùng: một phần request `/chat` trả lỗi 500 (`request_failed`), người dùng không nhận được câu trả lời.
- Ba bước kiểm tra đầu tiên:
  1. Xem panel `errors` để lấy breakdown `error_type` và giá trị `tool_success_rate_pct`.
  2. Lọc log `event == "request_failed"` trong khoảng bị ảnh hưởng, ghi lại `correlation_id` và `error_type` (thường là `RuntimeError` từ retrieval khi `tool_fail` bật).
  3. Mở trace tương ứng để xác nhận span nào ném lỗi (retrieval hay generation).
- Mitigation tạm thời: nếu do incident practice `tool_fail`, tắt bằng `python scripts/inject_incident.py --scenario tool_fail --disable`; nếu lỗi thật, trả fallback answer tĩnh cho `feature` bị ảnh hưởng trong lúc điều tra.
- Owner: platform-oncall

## Alert 3

- Tên: `quality_or_retrieval_degradation`
- Severity: warning
- Duration: 15m
- Kênh thông báo: Slack `#day13-l3a-oncall`
- SLI/SLO liên quan: guardrail `quality_score_avg_min: 0.75` và `retrieval_success_rate_pct_min: 90` trong `config/slo.yaml`.
- Điều kiện và thời gian duy trì: `quality_score_avg < 0.75` **hoặc** `retrieval_success_rate_pct < 90`, duy trì 15 phút (panel `quality` và phần `tool_success_rate_pct` của panel `errors`).
- Ảnh hưởng tới người dùng: câu trả lời kém liên quan hơn (thiếu context do retrieval fail) dù request vẫn trả 200, khó phát hiện bằng error rate.
- Ba bước kiểm tra đầu tiên:
  1. Xem panel `quality` và phần `tool_success` của panel `errors` để xác nhận xu hướng giảm và khoảng thời gian.
  2. Lọc log `response_sent` có `quality_score` thấp hoặc `tool_success == false`, lấy `correlation_id`.
  3. Mở trace, kiểm tra span `retrieve-context` (số doc trả về, `doc_count`) và metadata prompt (`prompt_name/label/version`) để loại trừ nguyên nhân do đổi prompt.
- Mitigation tạm thời: nếu do incident `cost_spike`/`rag_slow` ảnh hưởng gián tiếp tới chất lượng, tắt incident; nếu do prompt `candidate` mới rollout, rollback `production` về version trước theo `docs/PROMPT_VERSIONING.md`.
- Owner: ml-oncall
