# Waypoint Roadmap

Mục tiêu: Waypoint là hệ thống **monitor** (không trigger/schedule). Roadmap này bổ sung 3 tính năng để
trả lời đủ ba câu hỏi: *step nào hỏng và vì sao*, *chạy mất bao lâu*, *run đã làm gì*.

| # | Tính năng | Phụ thuộc | Thay đổi chính |
| --- | --- | --- | --- |
| 1 | Lỗi của step (failed + stack trace) ✅ | không | SDK + Monitor + UI |
| 2 | Thời lượng (duration) ✅ | không (tận dụng được #1) | Monitor + UI, SDK ít thay đổi |
| 3 | Log/event của run ✅ | #1 (lỗi là một loại event) | SDK + Monitor + UI |
| 4 | Freshness/SLA theo từng pipeline | #2 (dùng duration cho "chạy quá lâu") | SDK (spec) + Monitor + UI |
| 5 | Metric tuỳ chọn theo step | #3 (dùng chung kênh ghi của event) | SDK + Monitor + UI |
| 6 | Alerting (Slack/webhook/email) | #1, #4 (cần trạng thái Failed và Late) | Monitor + cấu hình |
| 7 | Map step / fan-out *(làm sau)* | #1, #2, #3, #5 (thêm chiều `item_key` vào các record đó) | SDK + Monitor + UI, đổi định dạng record |

Thứ tự đề xuất (#1–#3 đã xong): **1 → 2 → 3 → 4 → 5 → 6**. Mỗi tính năng là một spec riêng (speckit); #1–#3 và #4–#5 mỗi
nhóm có thể chung một bản phát hành SDK. #6 chỉ thay đổi Monitor.
#7 là giai đoạn sau, chỉ làm khi đạt các điều kiện ghi trong mục đó.

## Nguyên tắc chung (giữ nguyên)

- **Không lưu nội dung dữ liệu.** Chỉ tên, số đếm, thời gian và văn bản chẩn đoán ngắn do SDK tạo ra.
- **Lỗi Redis không bao giờ làm hỏng pipeline.** Mọi ghi mới đều bị nuốt lỗi và chỉ log cảnh báo.
- **Tương thích ngược.** Monitor mới đọc được run từ SDK cũ; monitor cũ bỏ qua key/field lạ. Field mới đều
  tuỳ chọn, và tăng `v` của record khi đổi định dạng.
- Monitor vẫn chỉ ghi các key `died`; mọi dữ liệu mới do SDK ghi.
- Mọi key có TTL theo `ttl_days` của run.

---

## 1. Lỗi của step (failed + stack trace) — ✅ Đã xong

**Trạng thái:** đã làm xong, spec `011-step-failure-errors`, phát hành `waypoint-etl 0.3.0`.

**Vấn đề hiện tại:** khi step raise exception, SDK để lại start marker và không ghi finish record
(`auditor.py`). Monitor không phân biệt được *Failed* với *Stalled* hoặc *Died*, và không có thông báo lỗi.

**Kết quả mong muốn:** step lỗi hiện trạng thái **Failed** ngay lập tức, kèm loại lỗi, thông báo và stack
trace rút gọn.

### SDK (`waypoint-etl`)
- [x] Bắt exception trong `audited_step`: ghi record lỗi rồi **re-raise nguyên bản** (không đổi kết quả hay
      exception của step, kể cả `async`).
- [x] Định dạng record lỗi, ví dụ `waypoint:{pipeline}:{env}:{run_id}:failed:{NN}-{step}`:
      `{"v":1, pipeline, env, run_id, step, index, failed_at, error: {type, message, traceback}}`.
- [x] Giới hạn kích thước: cắt `message` (~500 ký tự) và `traceback` (~8 KB, giữ các frame cuối).
- [x] Làm sạch: không đưa giá trị biến cục bộ vào traceback; thông báo lỗi có thể chứa dữ liệu nên cho phép
      tắt hoặc che bằng `init(capture_error_message=...)` và một hàm `redact` tuỳ chọn.
- [x] Khi step lỗi, xoá hoặc đánh dấu start marker để không bị hiểu là Running.
- [x] Test: lỗi được ghi, exception được re-raise nguyên vẹn, Redis hỏng thì không ảnh hưởng, sync và async.

### Monitor
- [x] Parse record `failed` (bỏ qua và đếm "unreadable" nếu hỏng, theo cách hiện tại).
- [x] Thêm trạng thái step **Failed** và trạng thái run **Failed**. Thứ tự ưu tiên trạng thái run:
      Running, **Failed**, Died, Stale, Incomplete, Lost data, Completed (cần xác nhận khi viết spec).
- [x] `/api/runs` và `/api/overview` trả thêm `error` của step lỗi.
- [x] Các step phía sau step lỗi hiện **Not reached**; run hiện "dừng tại step X".

### UI
- [x] Card Home: trạng thái Failed, ưu tiên cao nhất trong nhóm "cần chú ý".
- [x] Graph: node Failed (màu và biểu tượng riêng, không chỉ dựa vào màu).
- [x] Drawer của step: hiện loại lỗi, thông báo, stack trace (cuộn, có nút copy).
- [x] History: đánh dấu run Failed, thêm vào bộ lọc/trend nếu có.

### Khác với đề xuất ban đầu
- Start marker **không bị xoá**: Monitor cho failure ưu tiên hơn marker (so theo `index` của lần thử), nên
  store không cần thêm `delete` (research R6, R7).
- Run chỉ là **Failed** khi lỗi làm pipeline dừng (failure có `index` cao nhất của run); lỗi đã được bắt rồi
  chạy tiếp thì run là Incomplete (R8).
- Chỉ ghi `Exception`; không ghi `KeyboardInterrupt`/`SystemExit`/`CancelledError` (R1).
- `message` được lưu mặc định; tắt bằng `init(capture_error_message=False)` hoặc che bằng `redact` (R4).

### Tiêu chí hoàn thành
- Step raise exception → trong vài giây (không chờ heartbeat) Monitor hiện Failed kèm stack trace.
- Pipeline dùng SDK cũ vẫn hiển thị như trước.

---

## 2. Thời lượng (duration) — ✅ Đã xong

**Trạng thái:** đã làm xong cùng #3 trong spec `012-duration-and-run-events`, phát hành `waypoint-etl 0.4.0`.

**Hiện có:** step marker có `started_at` và finish record có `finished_at`, nên phần lớn tính được ở phía
Monitor mà không cần đổi định dạng.

**Kết quả mong muốn:** biết mỗi step và mỗi run chạy bao lâu, và thấy run chậm bất thường.

### SDK
- [x] Xác nhận finish record chứa cả `started_at` và `finished_at` (nếu thiếu thì thêm `duration_ms` đo bằng
      đồng hồ monotonic để không phụ thuộc lệch giờ).
- [x] Record `failed` của #1 cũng ghi `started_at` để tính thời gian đến lúc lỗi.

### Monitor
- [x] Tính `duration` cho từng step (done, failed) và cho cả run (từ step đầu đến step cuối hoặc đến bây giờ
      nếu đang chạy).
- [x] Step đang chạy: trả `elapsed` tính theo thời gian hiện tại.
- [x] `/api/runs` trả thêm `duration_ms` cho run và từng step.
- [x] Thống kê cho History: trung vị (p50) và p95 của thời lượng theo pipeline và môi trường, trong cửa sổ
      các run gần nhất.
- [x] Cờ **Slower than usual** khi một run vượt n lần trung vị (n cấu hình, mặc định ví dụ 2×).
      Đây là cảnh báo hiển thị, chưa phải thông báo gửi đi.

### UI
- [x] Run page: tổng thời lượng ở phần headline; thời lượng cạnh mỗi step trong List; nhãn thời lượng trên
      node Graph; làm nổi bật step chiếm phần lớn thời gian (bottleneck).
- [x] History: biểu đồ thời lượng theo thời gian cạnh trend số đếm; cột Duration trong danh sách run.
- [x] Card Home: hiện thời lượng của run mới nhất.
- [x] Định dạng dễ đọc (`1h 04m`, `37s`), và `…` khi đang chạy.

### Khác với đề xuất ban đầu
- Finish record **không** có `started_at` (marker hết hạn sau 24 giờ), nên SDK 0.4.0 ghi thêm `started_at` và
  `duration_ms` vào finish record. Run của SDK 0.2.0/0.3.0 chỉ có thời lượng step **ước lượng** (từ lúc step trước
  kết thúc, hiện `≈`); thời lượng cả run vẫn chính xác.
- API trả `duration_seconds` / `duration_approx` cho từng step và object `duration` cho run (không dùng `duration_ms`).
- Ngưỡng và cửa sổ là cấu hình **toàn cục**: `SLOW_RUN_MULTIPLE=2.0`, `DURATION_WINDOW_RUNS=30`,
  `DURATION_MIN_RUNS=5`; chỉ run đã hoàn tất (Completed, kể cả Lost data) được tính vào median/p95. Cờ chỉ ở mức run,
  không có cờ theo từng step và không đổi trạng thái hay nhóm "cần chú ý".

### Tiêu chí hoàn thành
- Mọi run đã hoàn tất, kể cả của SDK 0.2.0, hiện thời lượng đúng.
- Run chậm bất thường được đánh dấu trong History.

---

## 3. Log/event của run — ✅ Đã xong

**Trạng thái:** đã làm xong cùng #2 trong spec `012-duration-and-run-events`, phát hành `waypoint-etl 0.4.0`.

**Kết quả mong muốn:** một timeline theo run, để biết run đã làm gì và theo thứ tự nào, không cần mở log của
máy chạy. Bám nguyên tắc "không lưu nội dung dữ liệu": event là thông điệp ngắn do pipeline chủ động gửi.

### Mô hình event
- Một event: `{ts, level: info|warning|error, step?, message, fields?}`.
- Event do SDK tự sinh: run started, step started, step finished, step failed (từ #1), run finished/died
  (do Monitor suy ra khi hiển thị).
- Event do người dùng gửi: `waypoint_etl.log("Loaded batch 3", level="info", step="load", rows=1200)`.
- `fields` chỉ chấp nhận giá trị số/chuỗi ngắn, giới hạn số lượng và độ dài.

### SDK
- [x] API `waypoint_etl.log(message, *, level="info", step=None, **fields)` và `waypoint_etl.warn/error`.
      Gọi trước `init` hoặc khi init lỗi thì là no-op, không raise.
- [x] Lưu event vào Redis (Redis Stream hoặc List có giới hạn độ dài và TTL), key ví dụ
      `waypoint:{pipeline}:{env}:{run_id}:events`.
- [x] Giới hạn: số event tối đa mỗi run (ví dụ 500; khi vượt thì bỏ event `info` cũ nhất, giữ `warning` và
      `error`), độ dài message tối đa, ghi theo lô hoặc không chặn step.
- [x] Event tự sinh từ decorator (không cần người dùng sửa code).
- [x] Test: không chặn pipeline, giới hạn đúng, hỏng Redis không ảnh hưởng, an toàn khi đa luồng.

### Monitor
- [x] Endpoint đọc event của một run (có phân trang và lọc theo `level`, `step`), ví dụ
      `GET /api/runs/{pipeline}/{env}/{run_id}/events`.
- [x] Hợp nhất event tự sinh với event do người dùng gửi theo thời gian; thêm event suy ra (Died, Stalled).
- [x] Giữ quyền chỉ đọc của Monitor (cần thêm quyền `XRANGE`/`LRANGE` nếu dùng stream/list; cập nhật mục
      Security trong README).

### UI
- [x] Tab **Events** trong Run page: timeline theo thời gian, lọc theo level và step, tô màu theo level.
- [x] Từ node/step trong Graph, mở drawer và thấy event của step đó.
- [x] Run đang chạy: tự cập nhật event mới theo `REFRESH_SECONDS`.
- [x] Hiện số lượng warning/error trên card Home và dòng run trong History.

### Khác với đề xuất ban đầu
- Event do người dùng gửi lưu bằng **ba Redis List** mỗi run (`...:events:info|warning|error`, giữ 500/200/200 event
  mới nhất, `LTRIM` nên event info cũ nhất bị bỏ trước và error không bị đẩy ra), không dùng Stream. Monitor cần thêm
  quyền đọc `LLEN` và `LRANGE`; thiếu quyền thì mọi trang vẫn chạy, chỉ không có event của pipeline.
- Event tự sinh (run/step bắt đầu, kết thúc, lỗi, died, stalled) do **Monitor suy ra** từ các record đã có, SDK không
  ghi thêm: chạy đúng với mọi phiên bản SDK và không tốn lượt ghi.
- `waypoint_etl.log/warn/error` đi qua hàng đợi trong bộ nhớ và một luồng nền (không bao giờ chờ mạng hay raise);
  `capture_error_message` và `redact` áp dụng cho cả nội dung event (message và giá trị chuỗi).
- Số lượng warning/error trên card Home và dòng History chỉ đếm event do pipeline gửi; lỗi step đã thể hiện bằng
  trạng thái Failed. Endpoint: `GET /api/runs/{pipeline}/{env}/{run_id}/events` (lọc `level`, `step`, phân trang).

### Tiêu chí hoàn thành
- Run đang chạy cho thấy timeline event cập nhật gần thời gian thực.
- Lỗi của #1 xuất hiện trong timeline như một event `error`.
- Số event và dung lượng mỗi run bị chặn trên, kể cả khi pipeline log dồn dập.

---

## 4. Freshness/SLA theo từng pipeline

**Vấn đề hiện tại:** `STALE_HOURS=26` là một ngưỡng toàn cục. Pipeline chạy mỗi giờ sẽ không bao giờ bị báo
kịp, và pipeline chạy hằng tuần sẽ luôn bị báo Stale. Một run **không bao giờ bắt đầu** cũng không thể
phát hiện, vì Monitor chỉ thấy pipeline khi đã có dữ liệu.

**Kết quả mong muốn:** mỗi pipeline tự khai báo mức "đủ mới" của nó; Monitor báo **Late** khi vi phạm, kể cả
khi không có run nào xuất hiện.

### SDK
- [ ] Mở rộng `PipelineSpec` với phần SLA tuỳ chọn, ví dụ:
      `sla=Sla(expected_every="1h", grace="10m", must_finish_by="06:00", timezone="Asia/Ho_Chi_Minh", max_duration="45m")`.
- [ ] Ghi SLA vào flow description của run (field mới tuỳ chọn, tăng `v` nếu cần) để Monitor không phải cấu hình.
- [ ] Ghi thêm một key tồn tại lâu hơn TTL của run, ví dụ `waypoint:{pipeline}:{env}:meta` (SLA và lần chạy
      cuối), để Monitor vẫn biết pipeline tồn tại khi mọi run đã hết hạn. Key này chỉ chứa tên, SLA và thời gian.
- [ ] Validate trong `init`: giá trị sai thì cảnh báo và bỏ qua SLA, không chặn pipeline.

### Monitor
- [ ] Đọc SLA từ run mới nhất (hoặc key `meta`) và tính trạng thái **Late**:
      - đã quá `expected_every + grace` kể từ run bắt đầu gần nhất;
      - hoặc quá `must_finish_by` mà chưa có run hoàn tất trong chu kỳ hiện tại;
      - hoặc run đang chạy vượt `max_duration`.
- [ ] Phân biệt rõ trong dữ liệu trả về: *Late* (chưa chạy hoặc chạy trễ) với *Stale* (cơ chế cũ theo
      `STALE_HOURS`). Pipeline không khai báo SLA vẫn dùng `STALE_HOURS` làm mặc định.
- [ ] `/api/overview` trả `sla`, `next_expected_at`, `late_by`.
- [ ] Thêm Late vào thứ tự ưu tiên trạng thái (cần xác nhận khi viết spec).
- [ ] Xử lý múi giờ và giờ mùa hè đúng; dùng đồng hồ của Monitor (ghi rõ giới hạn lệch giờ như heartbeat).

### UI
- [ ] Card Home: hiện "Late 2h 10m" hoặc "Next expected 06:00"; Late nằm trong nhóm "cần chú ý".
- [ ] History: đánh dấu các lần vi phạm SLA, hiển thị tỉ lệ đạt SLA trong cửa sổ gần đây.
- [ ] Run page: hiện SLA đã khai báo và mức đạt/vi phạm của run này.

### Tiêu chí hoàn thành
- Pipeline chạy hằng giờ bị báo Late sau khoảng `expected_every + grace` nếu ngừng chạy, kể cả khi toàn bộ
  run đã hết TTL.
- Pipeline không khai báo SLA hoạt động như hiện nay.

---

## 5. Metric tuỳ chọn theo step

**Kết quả mong muốn:** ngoài số đếm in/out, pipeline gửi thêm vài con số có tên (số dòng bị reject, số lần
retry, số trang đã đọc...) để chẩn đoán sâu hơn, không lưu nội dung dữ liệu.

### SDK
- [ ] API `waypoint_etl.metric(name, value, *, step=None, mode="set")` với `mode` là `set`, `add` (cộng dồn)
      hoặc `max`. Có thể dùng ngay trong step đang chạy mà không cần truyền `step` (lấy step hiện tại).
- [ ] Giá trị chỉ là **số** (int/float). Tên hợp lệ theo mẫu giống tên step; giới hạn số metric mỗi step
      (ví dụ 20) và độ dài tên.
- [ ] Lưu trong record của step (hoặc key riêng
      `waypoint:{pipeline}:{env}:{run_id}:metrics:{NN}-{step}`), gộp khi ghi để không tăng số lần gọi Redis
      quá nhiều; step đang chạy cũng thấy được metric hiện có.
- [ ] Cho phép khai báo trước trong `StepSpec(metrics=(Metric("rejected", unit="rows", warn_above=100),))`
      để có nhãn, đơn vị và ngưỡng cảnh báo tuỳ chọn.
- [ ] No-op và không raise khi chưa `init`, init lỗi, hoặc Redis hỏng. An toàn khi đa luồng.
- [ ] Test: ba chế độ ghi, giới hạn, đa luồng, tương thích với record không có metric.

### Monitor
- [ ] Parse metric, bỏ qua và đếm "unreadable" khi hỏng. Trả trong `/api/runs` theo từng step.
- [ ] Đánh dấu metric vượt ngưỡng `warn_above`/`warn_below` đã khai báo (hiển thị cảnh báo, và là đầu vào
      của alerting #6).
- [ ] Với History: trung vị theo cửa sổ cho từng metric đã khai báo, để vẽ xu hướng.

### UI
- [ ] Drawer của step: bảng metric (tên, giá trị, đơn vị, cờ vượt ngưỡng).
- [ ] Graph/List: một badge nhỏ khi step có metric vượt ngưỡng.
- [ ] History: biểu đồ xu hướng cho metric đã khai báo, chọn metric trong danh sách.

### Tiêu chí hoàn thành
- Pipeline gọi `waypoint_etl.metric("rejected", 42)` thì giá trị xuất hiện trong drawer của step, kể cả khi
  step đang chạy.
- Metric vượt ngưỡng được đánh dấu trên run page.

---

## 6. Alerting (Slack/webhook/email)

**Vấn đề hiện tại:** chỉ biết có sự cố khi mở dashboard. Monitor đã tính sẵn trạng thái, nên chỉ cần phát hiện
**chuyển trạng thái** và gửi đi.

**Kết quả mong muốn:** nhận thông báo khi pipeline Failed, Died, Late, Lost data (hoặc metric vượt ngưỡng),
và khi đã hồi phục, mà không bị spam.

### Monitor
- [ ] Vòng lặp nền (độc lập với việc có người mở dashboard) tính trạng thái mỗi pipeline/env theo chu kỳ
      `ALERT_INTERVAL_SECONDS`.
- [ ] Phát hiện chuyển trạng thái: `healthy → problem` gửi cảnh báo; `problem → healthy` gửi "đã hồi phục".
      Cảnh báo cho từng run chỉ gửi một lần; nhắc lại sau `ALERT_REPEAT_HOURS` nếu vẫn chưa xử lý (0 = tắt).
- [ ] Lưu trạng thái đã báo để không gửi lại sau khi Monitor khởi động lại, ví dụ key
      `waypoint:alerts:{pipeline}:{env}` với `SET ... NX`/TTL (cần cập nhật quyền Redis và mục Security).
- [ ] **Chạy nhiều bản Monitor:** dùng khoá dạng `SET ... NX PX` để chỉ một bản gửi mỗi cảnh báo.
- [ ] Gom nhóm: nhiều pipeline lỗi cùng lúc thì gộp một tin, và có thời gian im lặng tối thiểu
      (`ALERT_COOLDOWN_SECONDS`) cho mỗi pipeline.
- [ ] Kênh gửi (mỗi kênh là một adapter nhỏ, có thể bật/tắt):
      - **Webhook** chung (JSON có version, tuỳ chọn ký HMAC);
      - **Slack** incoming webhook;
      - **Email** qua SMTP.
- [ ] Cấu hình bằng biến môi trường/file `.env`, ví dụ `ALERT_SLACK_WEBHOOK_URL`, `ALERT_WEBHOOK_URL`,
      `ALERT_SMTP_*`, `ALERT_ON=failed,died,late,lost_data`, `ALERT_ENVIRONMENTS=prod`. Mặc định **tắt**.
- [ ] Quy tắc theo pipeline (bỏ qua một pipeline, đổi kênh) đặt trong file cấu hình riêng của Monitor, không
      đưa vào SDK.
- [ ] Nội dung thông báo: tên pipeline, env, run id, trạng thái, step lỗi, thời lượng, và **liên kết** tới run
      page (`PUBLIC_BASE_URL`). Không đưa traceback đầy đủ vào kênh ngoài mặc định (chỉ loại lỗi và thông
      báo đã cắt ngắn), có thể bật qua cấu hình.
- [ ] Lỗi gửi (Slack hỏng, SMTP lỗi) chỉ log và thử lại có giới hạn; không ảnh hưởng việc phục vụ dashboard.
- [ ] Lệnh/endpoint thử nghiệm: `python -m app.alerts test` gửi một thông báo thử tới các kênh đã cấu hình.

### UI
- [ ] Trang hoặc phần "Alerts" chỉ đọc: kênh đang bật, các cảnh báo đã gửi gần đây, và cảnh báo đang mở.
- [ ] Trên card/run page hiện biểu tượng "đã gửi cảnh báo lúc ...".

### Tiêu chí hoàn thành
- Step lỗi hoặc pipeline Late gửi đúng một thông báo tới Slack/webhook/email đã cấu hình, và một thông báo
  hồi phục khi run kế tiếp thành công.
- Khởi động lại Monitor hoặc chạy hai bản Monitor không gây thông báo trùng.
- Tắt cấu hình alert thì Monitor hoạt động chính xác như trước.

---

## 7. Map step / fan-out (làm sau)

**Trạng thái:** ghi nhận, chưa lên lịch. Làm sau #1–#6 vì nó đổi định dạng record và thêm một chiều (`item_key`)
vào lỗi, duration, event và metric; làm trước sẽ phải làm lại các phần đó.

**Thuật ngữ:** pipeline hiện tại là **DAG**. Mô hình mới vẫn là DAG, nhưng một step lớn được mở rộng lúc chạy
thành N nhánh song song (**dynamic fan-out / fan-in**).

| Khái niệm | Tên dùng trong Waypoint |
| --- | --- |
| Step lớn lặp theo item | **Map step** (hoặc foreach) |
| DAG nhỏ bên trong | **Item flow** (subgraph chạy cho mỗi item) |
| Một lần chạy theo một item | **Item** (hoặc lane) |
| Số item chạy cùng lúc | `max_concurrency` |
| Bước gom kết quả | **Fan-in** |

Ví dụ: `A → B → [Map step "accounts": B1 → B2 → B3, max_concurrency=5] → C → D`.
`group` hiện tại chỉ là nhóm hiển thị, không phải map step.

### Khi nào mới làm
Hiện tại dùng cách tạm: các step cấp batch, bên trong tự chạy song song (thread pool/asyncio), kèm
metric (#5: `items_total`, `items_ok`, `items_failed`) và một event cho mỗi item lỗi có `item_key` (#1, #3).
Chỉ làm map step khi có **một trong các dấu hiệu**:
- thường xuyên phải mở log để biết item nào lỗi ở step con nào;
- cần retry hoặc chạy lại riêng từng item;
- thời lượng giữa các item chênh nhau nhiều và cần thấy item chậm;
- cần đếm in/out riêng cho từng item để phát hiện mất dữ liệu ở một item.

### SDK
- [ ] Khai báo trong spec, ví dụ `MapStepSpec("accounts", over="b", max_concurrency=5, steps=(StepSpec(...), ...))`;
      đưa vào flow description (tăng `v`).
- [ ] Ngữ cảnh item: `with waypoint_etl.item(key):` hoặc decorator, để các step con biết mình thuộc item nào
      (dùng `contextvars`, an toàn với thread và asyncio).
- [ ] `item_key` là id hoặc chỉ số ngắn, **không phải nội dung dữ liệu**; giới hạn độ dài và ký tự.
- [ ] Bỏ giả định "step chạy tuần tự": key `running` và `index` phải có thêm chiều item
      (ví dụ `...:running:{NN}-{step}:{item}`).
- [ ] Mọi record con (finish, failed, event, metric) mang `item_key`.
- [ ] Giới hạn quy mô: số item tối đa theo dõi chi tiết mỗi map step (ví dụ 1.000); vượt thì chỉ giữ tổng hợp
      và các item lỗi hoặc chậm.
- [ ] Heartbeat vẫn ở cấp run; item chạy ở process con vẫn là giới hạn đã biết.

### Monitor
- [ ] Trạng thái tổng hợp của map step: ví dụ "7/10 xong, 2 đang chạy, 1 lỗi"; Failed nếu có item lỗi chưa
      thay thế, Running nếu còn item đang chạy.
- [ ] Đếm in/out theo từng item và cộng gộp; phát hiện mất dữ liệu ở mức item.
- [ ] Duration: tổng của map step và phân bố theo item (p50, p95, item chậm nhất).
- [ ] API trả dạng tổng hợp theo mặc định, và danh sách item có phân trang, lọc theo trạng thái.

### UI
- [ ] Graph: map step là một node có thể mở rộng, hiện tiến độ (n/N) và số item lỗi; mở ra thấy item flow.
- [ ] Danh sách item có tìm, lọc (lỗi/đang chạy/chậm) và sắp xếp theo thời lượng; chỉ vẽ chi tiết item lỗi
      hoặc chậm khi N lớn.
- [ ] Drawer của item: các step con, số đếm, lỗi, event, metric của riêng item đó.

### Tiêu chí hoàn thành
- Map step với 10 item, concurrency 5, hiện tiến độ đúng khi đang chạy và chỉ ra chính xác item và step con
  bị lỗi.
- Map step với 10.000 item vẫn hiển thị nhanh và không làm đầy Redis (có giới hạn).
- Pipeline không dùng map step và SDK cũ không bị ảnh hưởng.

---

## Cần quyết định trước khi bắt đầu

1. ✅ *Đã quyết định (spec 011):* **Trạng thái Failed vs Died/Stalled:** step lỗi nhưng pipeline bắt lỗi và tiếp tục thì run có Failed không?
   (Đề xuất: Failed nếu có bất kỳ step failed chưa được thay thế bởi lần chạy lại thành công.)
2. ✅ *Đã quyết định (spec 011):* **Che dữ liệu nhạy cảm trong lỗi:** mặc định lưu `message` hay chỉ lưu `type` và traceback?
3. ✅ *Đã quyết định (spec 012):* **Cấu trúc lưu event:** Redis Stream (tiện phân trang) hay List (đơn giản, quyền đọc ít hơn)? → List, ba list theo level.
4. ✅ *Đã quyết định (spec 012):* **Phiên bản SDK:** `0.3.0` chỉ có #1; #2 và #3 cùng phát hành trong `0.4.0`.
5. ✅ *Đã quyết định (spec 012):* **Ngưỡng "chậm bất thường":** cấu hình toàn cục (chưa có theo từng `PipelineSpec`).
6. **SLA và `STALE_HOURS`:** Late có thay hẳn Stale cho pipeline đã khai báo SLA không, hay hai trạng thái
   cùng tồn tại?
7. **Key `meta` sống lâu hơn run:** có chấp nhận thêm một key ngoài TTL của run (để phát hiện "không bao giờ
   chạy") không? Nếu không thì Late chỉ áp dụng khi còn ít nhất một run trong Redis.
8. **Metric: lưu ở đâu?** Trong record của step (ít key hơn) hay key riêng (cập nhật được khi step đang chạy)?
9. **Alerting cần ghi vào Redis:** có chấp nhận cấp thêm quyền `SET` cho key `waypoint:alerts:*` không? Nếu
   không thì trạng thái "đã báo" chỉ nằm trong bộ nhớ và có thể báo lại sau khi khởi động lại.
10. **Email:** có thật sự cần SMTP không, hay Slack và webhook là đủ cho giai đoạn đầu?
11. **Xác thực dashboard:** liên kết trong thông báo trỏ tới dashboard; có làm xác thực trước khi bật alert
    ra ngoài mạng nội bộ không?
12. **Map step (khi làm):** N thường là bao nhiêu (10, 100, 10.000)? Có cần retry riêng từng item không? Kết
    quả fan-in tính là thành công khi tất cả item thành công, hay chấp nhận một phần?

## Ngoài phạm vi (cố ý không làm)

Trigger/re-execute/backfill, schedule và sensor (SLA chỉ *quan sát* lịch, không điều khiển lịch), quản lý người dùng và phân quyền, catalog asset toàn hệ
thống, lưu nội dung dữ liệu.
