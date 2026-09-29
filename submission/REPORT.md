# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Vũ Việt Hoàng
- **MSSV:** 2A202602398
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/ItzMeVHuangg/K4-L3-DAY13-VuVietHoang-2A202602398-Monitoring-LLMOps
- **Commit SHA cuối:** abd3aebcf7f362bc620c05cbe02feeb35772278c
- **Challenge ID:** day13-k4-l3a-monitoring-llmops-v1

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn | Trạng thái |
|---|---|---|
| Pytest cuối | `evidence/01-pytest.txt` | Đã có |
| Log validator | `evidence/02-log-validator.txt` | Đã có |
| Dashboard validator | `evidence/03-dashboard-validator.txt` | Đã có |
| Structured log | `evidence/04-structured-log.txt` | Đã có |
| PII redaction | `evidence/05-pii-redaction.txt` | Đã có |
| Trace list | `evidence/06-trace-list.png` | Đã có |
| Trace waterfall | `evidence/07-trace-waterfall.png` | Đã có (trace `fe0b49b255a419ec7f88541ad1d06992`) |
| Trace metadata | `evidence/08-trace-metadata.png` | Đã có |
| Prompt versions | `evidence/09-prompt-versions.png` | Đã có |
| Prompt rollback | `evidence/10-prompt-rollback.png` | Đã có |
| Dashboard runtime | `evidence/11-dashboard-overview.png` | Đã có (artifact gốc: https://claude.ai/artifact/ADJiDichcxKg4ogpwjfLVf) |
| Incident metric | `evidence/12-incident-metric.txt` | Đã có |
| Incident log | `evidence/13-incident-log.txt` | Đã có |
| Incident trace | `evidence/14-incident-trace.png` | Đã có |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | 100/100 | Baseline thiếu correlation_id + enrichment; sau CP1 không còn lỗi nào |
| `validate_dashboard.py` | 6/6 panel | 6/6 panel | Contract có sẵn trong starter; đã dựng thêm dashboard runtime thật |
| `pytest` | 22 passed | 25 passed | +3 test PII (cccd/credit_card/passport) và assertion child observation |
| Số traces hợp lệ | 0 (tracing tắt) | ≥ 39 trace/observation (AGENT+RETRIEVER+GENERATION mỗi request) | Xác nhận qua Langfuse API `observations.get_many` |
| Số PII leak | có leak (chưa scrub context ngoài payload) | 0 | Xác nhận bằng `validate_logs.py` (regex độc lập) và request thử với email/CCCD/thẻ/SĐT/passport giả |
| Latency P95 / TTFT P95 | n/a | ~152ms bình thường; ~2656ms khi có traffic bị `rag_slow` trộn vào cửa sổ | Xem panel `latency` trong dashboard artifact |
| Retrieval success rate | n/a | 100% (không có `tool_success=false` trong log cuối) | Panel `errors` |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `app/middleware.py` (`CorrelationIdMiddleware`) đọc header `x-request-id` nếu có, ngược lại sinh `req-<8-hex>` bằng `uuid.uuid4().hex[:8]`. Gọi `clear_contextvars()` đầu request để không rò context giữa các request, sau đó `bind_contextvars(correlation_id=...)`. ID được lưu vào `request.state.correlation_id` và trả lại qua header `x-request-id` + `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** `app/main.py` bind thêm `user_id_hash` (SHA-256 rút gọn, không log user_id thô), `session_id`, `feature`, `model`, `env` trước log `request_received`, nhờ vậy mọi log của cùng request đều có đủ context.
- **Cách bảo đảm PII được scrub trước khi ghi:** `app/logging_config.py` đăng ký processor `scrub_event` trong pipeline structlog, đặt trước `JsonlFileProcessor`/`JSONRenderer` cuối cùng để redact `event` và `payload` trước khi serialize/ghi file. `app/pii.py` có pattern cho email, số điện thoại VN, CCCD (12 số), thẻ thanh toán và hộ chiếu VN (`[A-Za-z]\d{7}`).
- **Cách kiểm chứng kết quả:** gửi request `/chat` chứa email/CCCD/thẻ/SĐT/passport giả, kiểm tra `data/logs.jsonl` không còn chuỗi gốc; chạy `python scripts/validate_logs.py` (dùng regex độc lập với `app/pii.py`) → 100/100, 0 PII leak.

## 5. Tracing và prompt versioning

- **Cấu trúc root/retrieval/generation observations:** `app/agent.py` (`LabAgent.run`) là root span `as_type="agent"` (qua decorator `@observe`). Bên trong, `retrieve()` được bọc bằng `langfuse_client.start_as_current_observation(name="retrieve-context", as_type="retriever", ...)` và `FakeLLM.generate()` bằng `as_type="generation"` (có `model`, `usage_details`, `cost_details`). Xác nhận qua Langfuse API: mỗi trace có đúng 3 observation AGENT → RETRIEVER, GENERATION (parent_observation_id trỏ về AGENT).
- **Cách nối trace với log:** `correlation_id` được set vào `metadata` của cả root span (qua `propagate_attributes(metadata={"correlation_id": ...})`) lẫn structlog context, nên cùng một giá trị `correlation_id` xuất hiện cả trong `data/logs.jsonl` và trong metadata của trace trên Langfuse — đã verify bằng API (`observations.get_many` filter theo `session_id`, đối chiếu `metadata.correlation_id` với log).
- **Prompt name:** `day13-chat` (biến `LANGFUSE_PROMPT_NAME`).
- **Version/label baseline:** version 1, label `baseline` (đồng thời gắn `production` lúc khởi tạo). Nội dung: `Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}`.
- **Version/label candidate:** version 2, label `candidate`. Thêm dòng chỉ dẫn "Answer in at most 2 concise sentences using only the provided Docs." so với v1.
- **Trace ID của mỗi version:** xác nhận qua metadata `prompt_version`/`prompt_label` trên từng trace (correlation_id tương ứng):
  - label=`baseline` → correlation_id `req-9402d6c1`, `prompt_version=1`.
  - label=`candidate` → correlation_id `req-ead7d0e8`, `prompt_version=2`.
  - `production` trước promote → correlation_id `req-008517e2`, `prompt_version=1`.
  - `production` sau promote → correlation_id `req-37708858`, `prompt_version=2`.
  - `production` sau rollback → correlation_id `req-e23a291d`, `prompt_version=1`.
- **Cách promote và rollback `production`:** dùng `langfuse_client.update_prompt(name="day13-chat", version=<n>, new_labels=[...])` để gán label `production` sang version khác (v2 để promote, v1 để rollback). App cache prompt theo `cache_ttl_seconds=60` (stale-while-revalidate) nên sau khi đổi label, request ngay sau đó có thể vẫn phục vụ version cũ; phải đợi hết TTL rồi gửi **thêm một request** mới thấy version mới — đây là điểm cần lưu ý khi vận hành (xem thêm mục 8).

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** dựng bằng script tự viết `scripts/build_dashboard.py`, đọc trực tiếp `data/logs.jsonl` theo đúng contract `config/dashboard.yaml` (nguồn dữ liệu, aggregation, threshold), render thành trang HTML tĩnh có đủ 6 panel: latency (P50/P95/P99 + TTFT), traffic, errors (+ retrieval success), cost, tokens, quality — mỗi panel hiển thị badge OK/BREACH so với threshold. `python scripts/validate_dashboard.py` → `HỢP LỆ: 6/6 panel`.
- **SLO và lý do chọn:** giữ nguyên SLO trong `config/slo.yaml` (`fast_successful_requests`, good event `latency_ms <= 3000`, target 99.5%/28 ngày) vì baseline thực đo P95 bình thường ~152ms, rất xa ngưỡng 3000ms — ngưỡng đủ chặt để bắt sự cố thật (như incident `rag_slow` kéo latency lên ~2.5-13s) mà không quá nhạy với dao động nhỏ của mock LLM (~150ms).
- **Cách tính error budget:** target 99.5% trong 28 ngày → error budget = 0.5% số request được phép chậm hơn 3000ms hoặc lỗi, tương đương guardrail `error_rate_pct_max: 2` được dùng làm ngưỡng cảnh báo sớm hơn SLO (2% > 0.5% budget) để có thời gian phản ứng trước khi budget cạn.
- **Ba alert và runbook tương ứng:** định nghĩa trong `config/alert_rules.yaml`, runbook chi tiết trong `docs/alerts.md`:
  1. `high_tail_latency` — `latency_p95_ms > 3000` trong 5m, severity critical, owner on-call-engineer.
  2. `elevated_error_rate` — `error_rate_pct > 2` trong 5m, severity warning, owner platform-oncall.
  3. `quality_or_retrieval_degradation` — `quality_score_avg < 0.75` hoặc `retrieval_success_rate_pct < 90` trong 15m, severity warning, owner ml-oncall.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4, seed 1311, `affected_feature=monitoring`, `latency_threshold_ms=2000`).
- **Khoảng thời gian điều tra:** `2026-09-29T09:24:50Z` → `2026-09-29T09:25:04Z` (chạy `scripts/inject_incident.py` rồi `scripts/load_test.py --challenge --concurrency 5`).
- **Triệu chứng từ metrics:** toàn bộ 5 request `feature=monitoring` trong cửa sổ trên có `latency_ms` 2651–2653ms, vượt `latency_threshold_ms=2000ms` của challenge (so với baseline bình thường ~150-155ms cho cùng loại request).
- **Log line và correlation ID liên quan:** lọc `data/logs.jsonl` theo `ts` trong cửa sổ trên, event `response_sent`, `feature=monitoring` → 5 correlation_id: `req-8f5ad6fa`, `req-2a0795cf`, `req-d98e3c7d`, `req-48d86d8c`, `req-b7680b4d`.
- **Trace ID và span gây ảnh hưởng:** trace của `req-8f5ad6fa` (trace_id `fe0b49b255a419ec7f88541ad1d06992`) có 3 observation: `RETRIEVER` (span `retrieve-context`) dài **2.5s**, `GENERATION` (span `generate-response`) chỉ 0.152s, `AGENT` root 2.655s. → span `retrieve-context` chiếm gần như toàn bộ latency tăng thêm. (Đã chạy 2 lần với cùng challenge config, kết quả cả hai lần đều khớp: retrieval là root cause, chênh lệch số liệu không đáng kể.)
- **Root cause:** incident `rag_slow` được Lab Coach cấu hình trong `challenge.json` bật flag `STATE["rag_slow"]=True`, khiến `app/mock_rag.py::retrieve()` `time.sleep(2.5)` trước khi trả kết quả — mô phỏng vector store/retrieval service bị chậm.
- **Fix action:** tắt incident bằng `python scripts/inject_incident.py --disable` (khôi phục hành vi bình thường ngay lập tức). Trong hệ thống thật: thêm timeout + fallback cho bước retrieval (trả context rỗng/cache gần nhất thay vì chờ vô hạn), và cân nhắc retry có giới hạn hoặc chuyển sang vector store dự phòng khi timeout.
- **Preventive measure:** alert `high_tail_latency` (`config/alert_rules.yaml`) sẽ cảnh báo khi `latency_p95_ms > 3000` duy trì 5 phút; với biên độ sự cố lần này (P95 cửa sổ hẹp ~2.65s, dưới ngưỡng 3000ms của SLO nhưng vượt ngưỡng riêng 2000ms của challenge) — đây là điểm cần cân nhắc thêm: có thể bổ sung một alert/threshold riêng theo từng `feature` (vd `monitoring`) thay vì chỉ theo P95 toàn hệ thống, để bắt được sự cố cục bộ sớm hơn.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** tách retrieval và generation thành hai child observation riêng (`as_type="retriever"` / `as_type="generation"`) thay vì gộp vào root span, vì rubric và thực tế điều tra incident đều cần biết *span nào* gây chậm/lỗi — nếu gộp chung, trace CP3 sẽ không phân biệt được retrieval chậm (rag_slow) hay generation chậm.
- **Một lỗi/blocker đã gặp:**
  1. Python 3.14 mặc định trên máy không có wheel sẵn cho `pydantic-core==2.33.2`, pip phải build từ Rust nhưng thiếu MSVC linker → chuyển sang venv Python 3.11.9 để dùng wheel có sẵn, không cần build.
  2. Khi test API đọc lại trace (`langfuse.api.observations.get_many`), field `usage_details`/`cost_details`/`input`/`output` của observation `GENERATION` luôn trả `None` dù code gọi đúng theo ví dụ chính thức của SDK (đã verify bằng script tối giản độc lập, không phụ thuộc code app). Ban đầu nghi ngờ đây là bug, nhưng khi mở trực tiếp trên Langfuse UI (evidence `07-trace-waterfall.png`) thì token (`121 tokens`) và cost (`$0.001395`) hiển thị đúng đầy đủ — kết luận: đây chỉ là giới hạn của REST API đọc lại (`observations.get_many`) trên vùng HIPAA cloud này, dữ liệu thực tế vẫn được ghi nhận đúng, không phải lỗi trong `app/agent.py`.
  3. Prompt cache trong SDK (`cache_ttl_seconds=60`) dùng kiểu stale-while-revalidate: sau khi promote/rollback label `production`, request ngay sau đó vẫn có thể trả version cũ; phải đợi hết TTL và gửi thêm 1 request nữa mới thấy version mới — ban đầu tưởng promote/rollback không hoạt động, sau khi kiểm tra trực tiếp qua `get_prompt()` mới xác nhận server-side đã đổi đúng, chỉ là cache client-side chưa refresh.
- **Cách tìm nguyên nhân và xử lý:** với cả 3 vấn đề trên đều dùng cách cô lập biến số — viết script Python tối giản gọi trực tiếp SDK/API (không qua FastAPI app) để loại trừ khả năng lỗi nằm ở code nghiệp vụ, sau đó so sánh kết quả trước/sau mỗi thay đổi.
- **Cách hiểu luồng Metrics → Logs → Traces:** Metrics (dashboard panel `latency`) cho biết *có* vấn đề và *khi nào* (P95 tăng trong một cửa sổ thời gian); Logs (`data/logs.jsonl` lọc theo `ts` + `event`) cho biết *request nào* bị ảnh hưởng qua `correlation_id`; Trace (Langfuse, tra theo đúng `correlation_id` đó trong metadata) cho biết *bước nào* trong request đó là nguyên nhân, qua so sánh duration giữa các child span (retriever vs generation).
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** prompt version cho phép biết chính xác request nào dùng bản prompt nào (cần thiết khi đổi prompt gây quality/cost thay đổi bất thường phải rollback nhanh); token/cost là cơ sở cho guardrail chi phí; SLO/error budget cho phép đặt threshold alert dựa trên tác động thực tế tới người dùng thay vì chỉ theo cảm tính.
- **Điều quan trọng nhất đã học:** một hệ thống "đã tạo trace" không có nghĩa là trace đó đủ chi tiết để điều tra — phải chủ động tách observation theo từng bước xử lý (retrieval/generation) thì mới trả lời được "bước nào là nguyên nhân" trong luồng Metrics → Logs → Traces.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** đủ 14/14 evidence trong `docs/SUBMISSION.md`. Không có phần nào chưa hoàn thành trong scope bắt buộc của lab.

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
