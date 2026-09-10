# Báo Cáo Phân Tích Lỗi Hệ Thống (Systematic Error Analysis)

Báo cáo này phân tích chi tiết các failure modes của hệ thống trên cả 2 chặng: **Retrieval** và **Generation**.

## 1. Retrieval Error Categories
Đánh giá trên N=300 mẫu truy xuất.

| Error Category | Count | Rate (%) | Mô tả |
|---|---:|---:|---|
| `retrieval_miss` | 79 | 26.3% | Gold evidence không xuất hiện trong top-20 candidates |
| `low_rank_after_top5` | 27 | 9.0% | Gold evidence có trong top-20 nhưng xếp sau rank 5 |
| `wrong_document` | 192 | 64.0% | Candidate rank-1 thuộc văn bản/chủ đề khác với gold |
| `semantic_mismatch` | 0 | 0.0% | Từ vựng câu hỏi đời thường không khớp thuật ngữ pháp lý |

### Chi Tiết Case Studies Truy Xuất:

#### Category: `retrieval_miss` (Ví dụ)
- **Câu hỏi**: Thời hiệu xử phạt đối với nhà xuất bản thực hiện xuất bản điện tử nhưng không được cơ quan nhà nước xác nhận đăng ký hoạt động là bao lâu?
  - Gold CIDs: `['63171']`
  - Retrieved Top-1: None

- **Câu hỏi**: Việc quản lý, sử dụng, khai thác giá trị đất được Nhà nước cho thuê được quy định như thế nào?
  - Gold CIDs: `['235283']`
  - Retrieved Top-1: None

- **Câu hỏi**: Phương thức phối hợp công tác giải quyết việc nuôi con nuôi đối với trẻ em đang được chăm sóc, nuôi dưỡng tại cơ sở trợ giúp xã hội được quy định như thế nào?
  - Gold CIDs: `['237675']`
  - Retrieved Top-1: None

#### Category: `low_rank_after_top5` (Ví dụ)
- **Câu hỏi**: Người học ngành điện công nghiệp trình độ cao đẳng sau khi tốt nghiệp có thể làm những công việc nào?
  - Gold CIDs: `['73585']`
  - Hit Rank: 10

- **Câu hỏi**: Quy trình chi tiết chỉ định nhà đầu tư đối với dự án cần bảo đảm yêu cầu về quốc phòng, an ninh quốc gia thực hiện như thế nào?
  - Gold CIDs: `['111113']`
  - Hit Rank: 6

- **Câu hỏi**: Việc báo cáo và gửi quyết định gia hạn thời gian kiểm tra công tác thi hành pháp luật về xử lý vi phạm hành chính được quy định như thế nào?
  - Gold CIDs: `['113408']`
  - Hit Rank: 6

#### Category: `wrong_document` (Ví dụ)
- **Câu hỏi**: Phó Tổng Giám đốc Ngân hàng Chính sách xã hội được xếp lương theo bảng lương như thế nào?
  - Gold CIDs: `['140864']`
  - Retrieved Top-1: None

- **Câu hỏi**: Thời hiệu xử phạt đối với nhà xuất bản thực hiện xuất bản điện tử nhưng không được cơ quan nhà nước xác nhận đăng ký hoạt động là bao lâu?
  - Gold CIDs: `['63171']`
  - Retrieved Top-1: None

- **Câu hỏi**: Việc quản lý, sử dụng, khai thác giá trị đất được Nhà nước cho thuê được quy định như thế nào?
  - Gold CIDs: `['235283']`
  - Retrieved Top-1: None

#### Category: `semantic_mismatch` (Ví dụ)
## 2. Generation Error Categories
Đánh giá trên N=200 mẫu sinh câu trả lời RAG.

| Error Category | Count | Rate (%) | Mô tả |
|---|---:|---:|---|
| `hallucination` | 0 | 0.0% | Câu trả lời có độ tin cậy thấp đối với evidence (faithfulness < 0.5) |
| `wrong_citation` | 0 | 0.0% | Trích dẫn sai văn bản hoặc thiếu căn cứ pháp lý rõ ràng |
| `incomplete_reasoning` | 0 | 0.0% | Câu trả lời ngắn, thiếu lập luận viện dẫn điều khoản |
| `over_refusal` | 0 | 0.0% | Từ chối trả lời dù tài liệu có thông tin liên quan |
| `format_non_compliance` | 0 | 0.0% | Không tuân thủ cấu trúc định dạng chuẩn |

### Chi Tiết Case Studies Sinh Lời Giải:

#### Category: `hallucination` (Ví dụ)
#### Category: `wrong_citation` (Ví dụ)
#### Category: `incomplete_reasoning` (Ví dụ)
#### Category: `over_refusal` (Ví dụ)
#### Category: `format_non_compliance` (Ví dụ)