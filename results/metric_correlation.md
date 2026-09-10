# Phân Tích Tương Quan Automatic Proxies vs Human Evaluation (Phase 8)

## 1. Bảng Tương Quan (Correlation Summary)
Đánh giá trên N=50 mẫu đánh giá song song giữa proxy tự động và human scoring (thang điểm 1-5).

| Metric Dimension | Auto Proxy (Mean) | Human Rating (Mean/5) | Pearson r | Spearman ρ |
|---|---:|---:|---:|---:|
| Citation Correctness | 1.0000 | 3.8800 | 0.0000 | 0.3385 |
| Grounding vs Faithfulness Proxy | 0.9522 | 4.9200 | -0.1899 | -0.1097 |

## 2. Phát Hiện Trọng Tâm (Key Empirical Finding): Lỗ Hổng Proxy Trích Dẫn

- **Tỷ lệ False Positives Citation**: Có **15/50** (30.0%) trường hợp metric tự động ghi nhận Citation Correctness tuyệt đối (= 1.00), nhưng con người chỉ đánh giá trích dẫn ở mức yếu (Score ≤ 3).
- **Nguyên nhân**: Proxy tự động chỉ kiểm tra sự xuất hiện bề mặt của chuỗi ký tự căn cứ pháp lý (`cid`, `Điều X`, v.v.), nhưng không xác minh được liệu điều khoản đó có thực sự hỗ trợ cho mệnh đề được kết luận hay không.
- **Ý nghĩa cho bài báo (Paper Research Direction)**: Đây là luận điểm nghiên cứu then chốt chứng minh rằng: *'High automatic citation presence does not guarantee authentic legal grounding'*, mở ra hướng nghiên cứu về **Evaluation of Evidence & Citation Verification in Vietnamese LegalQA** (Hướng 4).

### Các Trường Hợp False Positives Điển Hình:

1. **Câu hỏi**: Theo Khoản 1 Điều 6 của Luật Hộ tịch, những đối tượng nào có quyền và nghĩa vụ đăng ký hộ tịch?
   - Auto Citation: 1.0 | Human Citation Score: 3.0/5

2. **Câu hỏi**: Một công dân Việt Nam thường trú tại khu vực biên giới của Việt Nam muốn kết hôn với một công dân của nước láng giềng cũng thường trú tại khu vực biên giới với Việt Nam. Trong trường hợp này, cơ quan nào có thẩm quyền đăng ký kết hôn? Nếu một công dân Việt Nam đang cư trú tại nước ngoài muốn đăng ký khai sinh cho con của mình, cơ quan nào sẽ có thẩm quyền giải quyết?
   - Auto Citation: 1.0 | Human Citation Score: 3.0/5

3. **Câu hỏi**: Theo Điều 10 Luật Hộ tịch, giấy tờ do cơ quan có thẩm quyền của nước ngoài cấp để sử dụng cho việc đăng ký hộ tịch tại Việt Nam có yêu cầu chung gì?
   - Auto Citation: 1.0 | Human Citation Score: 3.0/5

4. **Câu hỏi**: Một công dân Việt Nam đang sinh sống tại Hoa Kỳ muốn đăng ký kết hôn tại Việt Nam bằng giấy chứng nhận kết hôn do cơ quan có thẩm quyền của Hoa Kỳ cấp. Theo Điều 10 Luật Hộ tịch, giấy tờ này cần trải qua thủ tục pháp lý nào trước khi có thể sử dụng để đăng ký hộ tịch tại Việt Nam, và có trường hợp ngoại lệ nào có thể áp dụng không?
   - Auto Citation: 1.0 | Human Citation Score: 3.0/5

5. **Câu hỏi**: Các quy định tại Khoản 1 và Khoản 2 Điều 8 Luật Hộ tịch có mối quan hệ như thế nào và cùng đóng góp ra sao vào việc bảo đảm quyền, nghĩa vụ đăng ký hộ tịch của cá nhân?
   - Auto Citation: 1.0 | Human Citation Score: 3.0/5
