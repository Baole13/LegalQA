# Knowledge Checklist va Mentor Q&A: Vietnamese LegalQA

Tai lieu nay dung de chuan bi cho buoi sharing 30-45 phut voi nguoi nghe co nen tang AI/ML. Muc tieu la giai thich duoc he thong end-to-end, bao ve cac quyet dinh ky thuat va phan biet ro ket qua da do duoc voi cac ket luan chua du bang chung.

## 1. Ban do buoi sharing

### Thong diep trung tam

> Du an la prototype Vietnamese LegalQA theo huong grounded RAG: truy xuat cac doan van ban phap luat, sap hang lai evidence, sau do dung extractive generator hoac Qwen de tao cau tra loi co can cu. Fine-tuning huong model vao cach tra loi va su dung evidence, khong thay the corpus hay bao dam do dung phap ly.

### Phan bo thoi gian goi y

| Thoi gian | Noi dung | Dieu nguoi nghe can nho |
|---|---|---|
| 0-3 phut | Bai toan va muc tieu | Legal QA can dung noi dung, dung can cu va dung pham vi evidence |
| 3-8 phut | Du lieu va preprocessing | Hai dataset co vai tro khac nhau; chunking ton trong cau truc dieu/khoan |
| 8-16 phut | Retrieval va QA-memory | Hybrid retrieval tang recall; QA-memory chi seed/boost evidence, khong tra loi truc tiep |
| 16-21 phut | Reranking | Cross-encoder tang chat luong top ranks nhung doi latency |
| 21-27 phut | Generation va QLoRA | Prompt-only, extractive va QLoRA la cac baseline co trade-off khac nhau |
| 27-33 phut | Evaluation va error analysis | Metric tu dong la proxy; retrieval miss van la nut that chinh |
| 33-38 phut | Demo | Theo dau mot request tu question den evidence va answer |
| 38-45 phut | Han che, roadmap va Q&A | Chua co expert legal validation hay temporal versioning hoan chinh |

Neu chi co 30 phut, rut cac phan retrieval, generation va evaluation moi phan con 4 phut; demo 3 phut va danh it nhat 5 phut cho Q&A.

### Data flow can ve duoc trong 2 phut

```text
thangvip ----------------> clean/normalize -> SFT train/val/test -> Qwen QLoRA adapter

yuitc train/corpus ------> legal chunking -> corpus artifacts -> sparse/model indexes
       |                                      |
       +-> QA alignment -> QA-memory ----------+-> hybrid candidate retrieval
       |                                      |          |
       +-> positives + hard negatives --------+          v
                                              heuristic rerank
                                                     |
                                          optional cross-encoder
                                                     |
question -> query expansion -> similar questions ----+-> top-k evidence
                                                            |
                                      extractive draft / reasoning prompt
                                                            |
                                      Qwen + optional LoRA, with fallback
                                                            |
                         answer + legal_basis + citations + debug information
```

Mot request runtime di qua `POST /ask`: validate schema, lay similar questions, hybrid retrieval, heuristic rerank, optional cross-encoder, build context, generate answer va tra ve ca output nguoi dung lan debug metadata.

## 2. Knowledge checklist

Danh dau `[x]` khi co the tu giai thich bang loi cua minh, dua ra ly do lua chon va noi duoc it nhat mot han che.

### 2.1. Bai toan va muc tieu

- [ ] **Dinh nghia bai toan:** dau vao la cau hoi phap ly tieng Viet; dau ra khong chi la cau tra loi ma con co `legal_basis`, reasoning ngan, citation, evidence va thong tin con thieu.
- [ ] **Giai thich grounding:** moi ket luan can suy ra tu evidence duoc retrieve. Grounded khong dong nghia voi dung phap ly neu evidence sai, het hieu luc hoac khong du.
- [ ] **Giai thich citation:** citation cho phep truy vet chunk/cid va metadata dieu, khoan. Citation presence chi cho biet co citation, khong tu dong chung minh citation ho tro ket luan.
- [ ] **Giai thich rui ro hallucination:** LLM co the them thong tin ngoai evidence, dien giai qua muc hoac gan sai can cu ngay ca khi cau van troi chay.
- [ ] **Bao ve kien truc RAG + fine-tuning:** RAG cap nhat va truy vet tri thuc; fine-tuning day format, directness, refusal va cach dung context. Hai phan giai quyet hai van de khac nhau.
- [ ] **Neu dung pham vi:** day la prototype nghien cuu va demo, chua phai he thong tu van phap ly san sang cho production.

**Cau chot nen noi:** "Toi toi uu he thong de dua cau tra loi ve dung evidence; toi khong coi fluency hay lexical overlap la bang chung cuoi cung cua do dung phap ly."

### 2.2. Du lieu va tien xu ly

- [ ] **Vai tro `thangvip`:** nguon chinh cho SFT reasoning/style, gom 29.145 mau sau chuan bi: 26.230 train, 1.457 validation, 1.458 test.
- [ ] **Vai tro `yuitc`:** nguon corpus retrieval, QA-memory, alignment, retriever/reranker training, retrieval evaluation va du kien RAFT grounding.
- [ ] **Quy mo artifacts:** 643.469 corpus chunks, 89.261 QA-memory records, 89.261 retrieval records va 357.044 reranker records theo tai lieu/trang thai du an.
- [ ] **Legal chunking:** uu tien ranh gioi article/clause; config dat `max_chars=1600`, `overlap_chars=120`. Muc tieu la giu don vi can cu va tranh cat dut logic phap ly.
- [ ] **Metadata:** can theo doi ten/so van ban, chuong, dieu, khoan, ngay ban hanh, ngay hieu luc va trang thai hieu luc. Hien corpus chua bao dam temporal validity day du.
- [ ] **Hard negatives:** lay cac top retrieved chunk kho nhung sai `cid`, loai positive chunk va cac chunk cung positive `cid`; mac dinh toi da 3 negatives/query. Cach nay day model phan biet cac van ban gan nghia.
- [ ] **Tach tap:** biet ro evaluation cua SFT test va retrieval test den tu dau; khong tron ket qua cua hai tap thanh mot benchmark duy nhat.
- [ ] **Leakage audit:** 1.458 eval questions duoc so voi 89.261 QA-memory questions; 0 exact duplicate, 0 normalized duplicate, 2 near-duplicates co similarity >= 0,9; max 0,9388.
- [ ] **Rui ro con lai:** audit similarity cau hoi khong loai tru leakage qua answer, corpus, document family hay cac bien the semantic duoi nguong.

**Trade-off:** chunk nho tang precision/citation locality nhung mat ngu canh; chunk lon giu ngu canh nhung lam retrieval va prompt nhieu noise. Overlap giam mat mach noi dung nhung tang duplicate candidates.

### 2.3. Retrieval

- [ ] **Sparse lexical branch:** `BM25Retriever` la ten vai tro trong pipeline, nhung implementation hien dung hashing-based word sparse matrix va matrix similarity; khong nen khang dinh day la BM25 cong thuc day du neu chua doi chieu index builder.
- [ ] **Char branch:** class `DenseRetriever` hien tim tren char vector sparse matrix. Dense embedding that nam o `OptionalEmbeddingRetriever` va `OptionalEmbeddingEnsembler`.
- [ ] **Model embeddings:** serving config co trained retriever path va ensemble BGE-M3/multilingual-E5; cac nhanh optional chi hoat dong khi model/artifact load duoc.
- [ ] **Query expansion:** query duoc chuan hoa/mo rong truoc khi chay cac retrieval source de tang lexical recall.
- [ ] **QA-memory:** tim cau hoi tuong tu, lay cac `cid` lien quan, seed mot so chunk vao candidate set va boost score theo similarity ket hop keyword/phrase coverage.
- [ ] **Fusion:** score gom lexical/char/Elasticsearch score, reciprocal rank-like bonus, keyword coverage, phrase coverage, direct-answer signal, QA boost va procedural-noise penalty. Trong config hien tai cac trong so chinh la BM25 0,5; char/dense 0,3; Elasticsearch 0,15; rank bonus 0,35; QA boost 0,8.
- [ ] **Preselection:** lay candidate tu moi nguon, merge theo `chunk_id`, preselect toi thieu 80 hoac `top_k * 8`, sau do cham model embedding neu kha dung.
- [ ] **Da dang evidence:** gioi han toi da 2 chunks tren moi `cid` trong serving config de tranh mot van ban chiem het top-k.
- [ ] **Top-k trade-off:** top-k lon tang kha nang chua gold evidence nhung tang context noise, token cost va nguy co model chon sai can cu.

**Metric can hieu:**

- `Recall@k`: ty le query co gold evidence trong top-k.
- `MRR`: trung binh nghich dao rank dau tien cua gold; thuong cao hon khi evidence dung nam gan dau.
- `Gold coverage in index`: gold evidence co ton tai trong index hay khong.
- `Conditional MRR`: MRR tren cac query ma gold co trong index; neu coverage = 1 thi bang MRR thong thuong.

### 2.4. Reranking

- [ ] **Heuristic reranker:** tong hop overlap, density, metadata, keyword/phrase coverage, direct-answer score, intent va procedural-noise penalty. Uu diem la nhanh, de debug; nhuoc diem la hand-crafted va kho generalize.
- [ ] **Cross-encoder:** cham truc tiep cap `[question, passage]`, hieu interaction tot hon bien doc lap nhung ton compute theo so candidate.
- [ ] **Training data:** positive la aligned gold passage; negatives la cac ket qua retrieval gan truy van nhung khac positive `cid`.
- [ ] **Runtime:** pipeline luon chay heuristic truoc, sau do `OptionalCrossEncoderReranker`; neu `models/reranker-best` va dependency load duoc thi dung model, neu khong tra ve heuristic candidates.
- [ ] **Trang thai artifact:** repo hien co `models/reranker-best`; van can xem `/health` hoac response `system.reranker_mode` de khang dinh mode cua process dang demo.
- [ ] **Ket qua:** tren 300 retrieval samples, cross-encoder dua Recall@5 tu 0,5100 len 0,6133; Recall@20 tu 0,6533 len 0,7033; MRR tu 0,3859 len 0,4648 so voi full heuristic row.
- [ ] **Khong overclaim:** day la mot run 300 mau, chua co confidence interval, significance test, latency benchmark hay nhieu seed.

### 2.5. Generation va grounding

- [ ] **Extractive baseline:** tao draft/cau tra loi tu evidence va co structured output on dinh; la baseline manh cho grounding va format.
- [ ] **Prompt-only Qwen:** base Qwen2.5-7B-Instruct doc top evidence ma khong nap adapter SFT.
- [ ] **QLoRA variant:** base model cong adapter `models/qwen2.5-7b-legalqa-qlora` de hoc output style/task behavior.
- [ ] **Reasoning prompt:** chi dua toi da 5 evidence chunks, yeu cau JSON-only, toi da 2 can cu/trich dan, direct answer va `Toi khong biet` khi thieu evidence.
- [ ] **Structured response:** `answer`, `legal_basis`, `reasoning`, `missing_info`, `citation_chunk_ids`, `confidence`, `reason`; API bo sung quotes, evidence, retrieval va system debug.
- [ ] **Parsing va fallback:** reasoner thu parse JSON truc tiep, fenced JSON roi object substring. Neu generation/parse khong dung, generator co the fallback extractive hoac `forced_raw` trong luong ep LLM.
- [ ] **Format compliance thap:** LLM co the tra prose co noi dung hop ly nhung khong dung schema. Vi vay citation/faithfulness proxy cao van co the song song voi format compliance gan 0.
- [ ] **Ba khai niem khac nhau:** lexical similarity do giong gold answer; grounding do muc ho tro boi evidence; legal correctness can ca evidence dung, con hieu luc va suy luan dung.

### 2.6. Fine-tuning

- [ ] **Muc tieu SFT:** hoc directness, citation/refusal va structure, khong dung adapter lam kho tri thuc phap luat chinh.
- [ ] **QLoRA:** base weights duoc load 4-bit NF4; chi train low-rank adapters, giam VRAM va chi phi so voi full fine-tuning.
- [ ] **Hyperparameters can nho:** Qwen2.5-7B-Instruct, sequence length 4.096, 3 epochs, batch/device 2, gradient accumulation 8, learning rate `2e-4`, BF16, LoRA `r=16`, alpha `32`, dropout `0,05`.
- [ ] **Target modules:** attention projections `q/k/v/o` va MLP projections `gate/up/down`.
- [ ] **SFT vs RAFT:** SFT hoc mapping instruction/context sang answer theo data style; RAFT train model suy luan tren positive evidence kem distractors va tu choi khi evidence khong du.
- [ ] **Trang thai RAFT:** co config va `raft_sft.jsonl`, nhung dataset/run chua duoc xem la hoan thien; khong trinh bay RAFT nhu mot ket qua da duoc xac nhan.
- [ ] **Rui ro:** overfit theo template/dataset, catastrophic forgetting, hoc shortcut citation, exposure bias va chat luong output bi chan boi chat luong retrieval.

### 2.7. Evaluation va tinh hop le

#### Bang so lieu can nho

| Nhom | Variant / mau | Metric chinh | Cach phat bieu an toan |
|---|---|---|---|
| Retrieval | Cross-encoder, N=300 | R@1 0,3500; R@5 0,6133; R@20 0,7033; MRR 0,4648 | Tot hon cac ablation trong run hien tai |
| Generation | QLoRA, N=200 | Token F1 0,5909; ROUGE-L 0,4808 | Lexical metrics tren SFT test set |
| End-to-end | QLoRA + retrieved context, N=200 | F1 0,5474; ROUGE-L 0,4092; faithfulness proxy 0,9408 | Proxy grounding, khong phai legal accuracy |
| Baseline | Extractive, N=200 | F1 0,5478; format 0,986; reasoning proxy 0,7666 | Structured va on dinh, van phu thuoc retrieval |
| Human eval | 75 examples, 2 annotators | Legal correctness mean 4,5133/5; grounding 3,92/5 | Preliminary; annotators khong phai chuyen gia luat |
| Leakage | 1.458 x 89.261 questions | 0 exact/normalized; 2 near-duplicates >= 0,9 | Giam mot lo ngai, khong chung minh sach leakage hoan toan |

- [ ] **Exact Match:** qua khat khe voi generative QA; 0 khong dong nghia moi answer sai.
- [ ] **Token F1/ROUGE-L:** do lexical overlap, co the phat mot paraphrase dung va thuong mot cau sai nhung giong gold.
- [ ] **Faithfulness/citation/directness/refusal:** hien la heuristic proxy; can doc rule cham diem truoc khi dien giai.
- [ ] **Format compliance:** do adherence vao output structure, khong do legal correctness.
- [ ] **Human evaluation:** 75 examples, 2 annotators doc lap sau calibration ngan; cac annotator khong phai legal experts; agreement la descriptive statistics, khong phai Cohen's kappa/Krippendorff alpha.
- [ ] **Error analysis:** retrieval run co 89/300 `retrieval_miss` va 27/300 `low_rank_after_top5`; day la bang chung retrieval van la nut that.
- [ ] **Khong tron sample size:** retrieval table N=300, generation N=200, schema smoke N=5, human evaluation N=75.
- [ ] **Khong dung ket qua pending:** end-to-end human evaluation 50 mau van `pending_annotations`.
- [ ] **Khong dung schema smoke de ket luan:** 5 mau va format compliance 0 khong du de noi schema prompting cai thien he thong.

### 2.8. Production va han che

- [ ] **Startup:** FastAPI build/load pipeline va artifacts; UI la static frontend. Health endpoint phai duoc kiem tra truoc demo.
- [ ] **API:** `POST /ask` nhan `question`, `top_k` 1-10, `force_llm_reasoning`, `debug_llm`; response chua ca user output va debug payload.
- [ ] **Lazy/optional models:** Qwen lazy-load khi can; model retriever, ensemble, Elasticsearch va cross-encoder co the khong kha dung tuy environment.
- [ ] **Latency:** lexical retrieval nhanh; embedding/cross-encoder tang compute; Qwen 7B la thanh phan ton latency/VRAM nhat. Repo chua co latency percentile benchmark de dua con so production.
- [ ] **Failure behavior:** cross-encoder fallback ve heuristic; LLM failure/invalid JSON co the fallback extractive. Can quan sat `generator_mode`, `reason`, `llm_debug` va `system` thay vi chi nhin answer.
- [ ] **Bao mat/van hanh:** can them authentication, rate limiting, input/output audit, model/index versioning, monitoring, timeout va resource controls neu product hoa.
- [ ] **Temporal validity:** metadata co truong ngay/trang thai nhung retrieval chua bao dam loc dung van ban con hieu luc tai thoi diem cau hoi.
- [ ] **Roadmap uu tien:** expert legal evaluation; corpus/version validity; giam retrieval misses; benchmark latency; hoan thien RAFT; calibration confidence/refusal.

## 3. Demo script 3-5 phut

### Chuan bi truoc buoi sharing

1. Khoi dong server va cho den khi startup hoan tat.
2. Goi `/health`; ghi lai `chunks`, retriever/reranker mode va LLM availability.
3. Chay truoc hai cau hoi demo voi cung config se dung trong buoi sharing.
4. Luu JSON response cua ca hai request lam fallback; chup UI o answer va debug evidence.
5. Khong restart model ngay truoc luc demo neu Qwen can cold start lau.

### Case A: evidence ro rang

Dung cau hoi:

> Theo Khoan 1 Dieu 57 Luat Ho tich, Co so du lieu ho tich co tinh chat la gi?

Request mau:

```bash
curl -s http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Theo Khoan 1 Dieu 57 Luat Ho tich, Co so du lieu ho tich co tinh chat la gi?","top_k":5,"force_llm_reasoning":true,"debug_llm":true}'
```

Thu tu trinh bay:

1. Chi ra cau tra loi truc tiep: "tai san quoc gia".
2. Mo can cu/citation va doi chieu text evidence, khong chi doc answer.
3. Mo debug retrieval: `cid`, hybrid/rerank score, sources va top-k.
4. Chi ra `system.reranker_mode` va `generator_mode` de xac nhan request dung component nao.
5. Giai thich rang mot case dung chi minh hoa traceability, khong chung minh metric tong the.

### Case B: evidence khong du

Dung mot cau hoi ngoai corpus, co thong tin bien dong:

> Theo quy dinh co hieu luc ngay hom nay, gia ve may bay tu Ha Noi den Tokyo ngay mai la bao nhieu?

Ky vong: he thong neu "Toi khong biet" hoac chi ro thieu can cu, confidence thap va khong tao citation gia. Neu he thong van tra loi, dung chinh failure nay de noi ve refusal calibration thay vi che giau no.

### Phuong an fallback

- Mo JSON da luu va anh debug thay cho live generation.
- Neu Qwen khong load, demo extractive fallback va chi vao `generator_mode`/`llm_debug`.
- Neu cross-encoder khong load, noi ro heuristic fallback va khong tuyen bo live request dung model reranker.
- Neu index loi, dung report/case study co san; khong reindex trong luc sharing.

## 4. Ngan hang cau hoi mentor

Moi cau tra loi mau duoc thiet ke cho 30-60 giay. Sau cau dau tien, uu tien noi them mot bang chung va mot han che.

### Muc 1: Kien thuc nen

#### Q1. Tai sao bai toan nay can RAG?

**Tra loi mau:** Luat la tri thuc lon, can truy vet va co the thay doi. Neu chi dua vao tham so LLM, ta kho biet model dua vao van ban nao va kho cap nhat. RAG dua cac doan can cu vao context, cho phep citation va cap nhat corpus doc lap voi model. Fine-tuning van huu ich, nhung chu yeu de hoc cach dung evidence va format tra loi.

**Bang chung:** Response co `citations`, `evidence`, `retrieval`; prompt cam dua thong tin ngoai evidence.

**Khong nen noi:** "RAG loai bo hallucination."

**Hoi tiep co the gap:** Neu retrieve sai thi sao? Khi do generation bi gioi han boi evidence sai; can retrieval evaluation, refusal va expert review.

#### Q2. Grounding khac legal correctness nhu the nao?

**Tra loi mau:** Grounding hoi ket luan co duoc evidence ho tro khong. Legal correctness con doi hoi evidence la van ban dung, con hieu luc, ap dung dung doi tuong va suy luan dung. Mot answer co the grounded vao van ban het hieu luc nen van sai phap ly.

**Bang chung:** Faithfulness trong report duoc ghi ro la proxy; human annotators khong phai chuyen gia luat.

**Khong nen noi:** Faithfulness 0,9408 nghia la legal accuracy 94,08%.

#### Q3. Vi sao chunk theo dieu/khoan thay vi fixed token?

**Tra loi mau:** Dieu va khoan la don vi nghia va citation tu nhien cua van ban phap luat. Giu ranh gioi nay giup evidence de doc, de cite va it tron cac quy dinh khong lien quan. Gioi han ky tu va overlap van can cho cac don vi qua dai.

**Bang chung:** Config uu tien `article`, `clause`, `max_chars=1600`, overlap 120.

**Hoi tiep:** Da ablate chunk size chua? Chua co ablation chunk-size day du, nen kich thuoc hien tai la engineering choice can duoc benchmark them.

#### Q4. BM25 va dense retrieval bo sung nhau ra sao?

**Tra loi mau:** Sparse retrieval manh khi truy van co tu khoa, so dieu, ten van ban trung khop; semantic embedding tot hon voi paraphrase. Hybrid giu precision cua lexical match va tang recall cho cach dien dat khac nhau.

**Can chinh xac:** Branch `BM25Retriever` hien la hashing-based word sparse search; `DenseRetriever` hien la char sparse search. Dense neural retrieval nam o cac optional model retriever/ensemble.

#### Q5. Recall@k va MRR noi cho ta dieu gi?

**Tra loi mau:** Recall@k cho biet bao nhieu cau co gold evidence trong top-k, quan trong vi generator khong the dung evidence neu evidence vang mat. MRR nhay voi vi tri cua ket qua dung, nen phan anh kha nang dat can cu dung len dau. Hai metric khong danh gia answer cuoi cung.

**Hoi tiep:** Tai sao conditional MRR bang MRR? Trong run nay gold coverage trong index bang 1, nen tap dieu kien trung voi toan bo tap.

#### Q6. Cross-encoder khac bi-encoder nhu the nao?

**Tra loi mau:** Bi-encoder ma hoa query va passage doc lap, phu hop search quy mo lon. Cross-encoder doc chung cap query-passage, bat interaction chi tiet tot hon nhung phai forward cho tung candidate. Vi vay du an retrieve rong truoc roi moi cross-encode mot tap nho.

**Bang chung:** Cross-encoder cai thien MRR tu 0,3859 len 0,4648 trong run N=300.

### Muc 2: Quyet dinh thiet ke

#### Q7. QA-memory co phai la cach copy answer cu khong?

**Tra loi mau:** Trong runtime, QA-memory tim cau hoi gan, lay `cid` lien quan de seed/boost corpus chunks; answer van duoc tao tu evidence. No la retrieval prior, khong phai direct answer cache. Tuy nhien neu QA-memory chua eval duplicates thi metric co the bi thoi phong, nen du an co leakage audit.

**Bang chung:** 0 exact/normalized duplicate, 2 near-duplicates >= 0,9.

**Khong nen noi:** Audit nay chung minh tuyet doi khong co leakage.

#### Q8. Tai sao QA boost con nhan coverage/phrase coverage?

**Tra loi mau:** Similar question co the gan ve hinh thuc nhung sai pham vi phap ly. Modulate boost boi overlap cua query voi chunk lam giam viec mot QA hit manh keo len evidence khong truc tiep lien quan. Day la heuristic trade-off, can ablation de xac nhan tung thanh phan.

#### Q9. Tai sao gioi han hai chunks tren moi `cid`?

**Tra loi mau:** Mot van ban dai co the sinh nhieu chunk rat giong nhau va chiem het top-k. Gioi han theo `cid` tang da dang can cu. Mat trai la cau hoi can nhieu khoan cung mot van ban co the bi mat context, nen con so hai la tham so can benchmark.

#### Q10. Tai sao can heuristic reranker neu da co cross-encoder?

**Tra loi mau:** Heuristic la stage loc/giai thich duoc va la fallback khi model artifact hay dependency khong kha dung. Cross-encoder chi cham candidates sau heuristic de kiem soat latency. Cach nay cung cho phep ablation va van hanh demo on dinh hon.

#### Q11. Hard negatives duoc chon nhu the nao?

**Tra loi mau:** Voi moi query-positive pair, lay cac top retrieval candidates khac positive chunk va khac positive `cid`, deduplicate roi lay toi da ba. Chung gan query hon random negatives, nen day retriever/reranker phan biet nhung quy dinh de nham lan.

**Han che:** False negatives van co the xay ra neu mot `cid` khac cung la can cu hop le nhung dataset khong gan nhan.

#### Q12. Vi sao top-k evidence mac dinh la 5?

**Tra loi mau:** Day la diem can bang recall, context noise, token budget va latency. Prompt builder cung cat tai 5 chunks. Top-k ablation cho thay Recall@5 0,51 o full heuristic va tang tiep khi k lon hon, nhung generation chua co full quality/latency sweep theo k, nen khong coi 5 la toi uu toan cuc.

#### Q13. Tai sao response tra ca debug metadata cho client?

**Tra loi mau:** Prototype nghien cuu can traceability: biet chunk nao duoc retrieve, score ra sao, component nao dang chay va LLM co fallback khong. Trong production nen tach user contract khoi internal debug, gioi han thong tin va bao ve du lieu.

### Muc 3: Fine-tuning va phan bien thuc nghiem

#### Q14. SFT va RAFT khac nhau o diem nao?

**Tra loi mau:** SFT cua du an hoc task format va phong cach reasoning tu du lieu thangvip. RAFT can positive evidence cung distractors de model hoc chon can cu, lap luan tren context va tu choi khi khong du. RAFT artifact/config da co nhung chua hoan thien va chua co ket qua du de so san.

**Khong nen noi:** He thong hien tai da duoc RAFT va RAFT tot hon SFT.

#### Q15. Vi sao dung QLoRA thay vi full fine-tuning?

**Tra loi mau:** QLoRA luong tu hoa base model 4-bit va chi train low-rank adapters, phu hop mot GPU va giam VRAM. Voi prototype, no cho phep thu nghiem nhanh ma van giu base model. Trade-off la phu thuoc quantization, target modules va capacity cua adapter.

#### Q16. LoRA `r=16`, alpha 32 co y nghia gi?

**Tra loi mau:** Rank quyet dinh capacity cua low-rank update; alpha scale tac dong adapter. Cau hinh `r=16`, alpha 32 la diem khoi dau thuc dung, khong phai ket qua hyperparameter optimization. Can sweep va theo doi validation/generalization de bao ve lua chon tot nhat.

#### Q17. Fine-tuning co lam model hoc thuoc luat khong?

**Tra loi mau:** Co kha nang model ghi nho mau train, nhung muc tieu thiet ke khong phai dung weights lam knowledge base. Runtime van yeu cau evidence va citation. Can kiem tra held-out data, leakage va test khi evidence bi thieu/xung dot de xem model co dua vao memory ngoai context khong.

#### Q18. Vi sao QLoRA co F1 cao hon prompt-only nhung directness thap hon?

**Tra loi mau:** QLoRA co the hoc cach dien dat dai va gan gold answer hon, lam F1/ROUGE tang, nhung verbosity lam directness proxy giam. Day minh hoa multi-objective trade-off: lexical match, directness, grounding va format khong di cung nhau.

**Bang chung:** QLoRA F1 0,5909/directness 0,74; prompt-only F1 0,4994/directness 0,995 tren baseline report.

#### Q19. Tai sao format compliance gan 0 ma van dung `forced_raw`?

**Tra loi mau:** Model thuong tra prose thay vi JSON hop le. `forced_raw` giu noi dung LLM cho demo khi ep reasoning, trong khi pipeline van can structured fields tu fallback/normalization. Day la resilience mechanism, khong phai loi giai cuoi; production can constrained decoding, repair/validation va test schema nghiem ngat.

#### Q20. Cac metric proxy co the bi game khong?

**Tra loi mau:** Co. Citation presence co the tang neu model chen citation bat ky; lexical faithfulness co the thuong copy evidence; refusal quality co the cao neu model tu choi qua nhieu. Vi vay can metric ket hop, error analysis va expert human evaluation, khong toi uu mot con so don le.

#### Q21. Ket qua co statistically significant khong?

**Tra loi mau:** Chua the khang dinh. Report hien co point estimates tren 300 retrieval va 200 generation samples, chua co bootstrap confidence intervals, paired significance tests hay multiple seeds. Cach phat bieu dung la "cai thien trong run hien tai", khong phai "chung minh vuot troi".

#### Q22. Human evaluation da du tin cay chua?

**Tra loi mau:** No cung cap tin hieu bo sung tren 75 examples voi hai annotators doc lap, nhung hai nguoi khong phai chuyen gia luat. Agreement hien tai la descriptive, chua co formal reliability coefficient. Do do day la preliminary assessment, chua phai legal validation.

#### Q23. Leakage audit da du chua?

**Tra loi mau:** Chua. No loai tru exact va normalized duplicates, dong thoi phat hien hai near-duplicates tren nguong 0,9. Van can kiem tra overlap theo answer/evidence/document, semantic clusters, split provenance va chay sensitivity analysis sau khi loai cac near-duplicates.

#### Q24. Vi sao Exact Match bang 0 ma he thong van co gia tri?

**Tra loi mau:** Generative answer co nhieu cach dien dat nen exact string match qua khat khe. F1, ROUGE, grounding/citation va human review cho nhieu goc nhin hon. Tuy nhien khong nen bo EM chi vi no thap; no van la diagnostic cho format/normalization va cac cau tra loi ngan.

### Muc 4: Failure va production

#### Q25. Nut that lon nhat hien tai la gi?

**Tra loi mau:** Retrieval miss. Trong error analysis, 89/300 query khong co gold evidence o retrieved top-20 du gold co trong index, va 27/300 bi xep sau top-5. Generator khong the sua mot cach dang tin cay khi can cu dung khong duoc dua vao context.

#### Q26. Mot retrieved passage co ve lien quan nhung gold lai la passage khac, xu ly sao?

**Tra loi mau:** Co the la retrieval failure that, gold annotation thieu, hoac nhieu evidence cung hop le. Can manual adjudication theo query: kiem tra tinh ho tro, hieu luc va pham vi, sau do bo sung multi-positive labels neu can. Chi dua `cid` match co the danh gia thieu cac can cu tuong duong.

#### Q27. He thong xu ly van ban het hieu luc nhu the nao?

**Tra loi mau:** Metadata co `effective_date` va `validity_status`, nhung runtime retrieval chua cho thay co che temporal filtering day du theo thoi diem cau hoi. Day la han che quan trong. Production can versioned corpus, ngay ap dung trong query va conflict resolution giua cac phien ban.

#### Q28. Neu cross-encoder hoac Qwen khong load duoc thi sao?

**Tra loi mau:** Cross-encoder optional va fallback ve danh sach heuristic; Qwen lazy-load va generator co extractive fallback khi model/parse that bai. Response `system`, `generator_mode` va `llm_debug` giup phat hien mode thuc te. Can metrics/alerts de fallback khong dien ra am tham trong production.

#### Q29. Confidence hien tai co duoc calibration khong?

**Tra loi mau:** Chua co bang chung calibration nhu reliability diagram, ECE hay selective-risk curve. Confidence tu model/heuristic chi nen dung nhu tin hieu giao dien, khong phai xac suat dung. Roadmap can calibrate theo retrieval score, evidence support va expert labels.

#### Q30. Neu dua len production, ba viec dau tien la gi?

**Tra loi mau:** Mot la corpus versioning va temporal validity. Hai la expert legal evaluation voi rubric va escalation policy. Ba la observability/guardrails: latency, fallback rate, retrieval coverage, citation support, authentication, audit log va human review cho case rui ro cao.

#### Q31. Lam sao giam latency?

**Tra loi mau:** Profile tung stage truoc. Sau do co the cache/index retrieval, giam candidate depth, batch cross-encoder, quantize/serve LLM hieu qua, stream output va route cau de sang extractive mode. Moi toi uu can theo doi recall va grounding de khong doi chat luong lay toc do.

#### Q32. Tai sao khong dung Elasticsearch trong demo?

**Tra loi mau:** Config hien tai dat Elasticsearch `enabled=false`, nen no la optional integration, khong phai thanh phan tao ra ket qua chinh. Artifact-based local retrieval giup prototype tu chua. Neu bat Elasticsearch, can benchmark va report nhu mot variant rieng.

#### Q33. Roadmap nghien cuu hop ly nhat la gi?

**Tra loi mau:** Truoc het giam retrieval misses va lam sach evaluation provenance. Tiep theo hoan thien RAFT va ablation co paired confidence intervals. Cuoi cung thuc hien expert legal evaluation, temporal-validity tests va end-to-end latency/cost benchmark. Thu tu nay xu ly nut that evidence truoc khi toi uu generator.

## 5. Case study nen ke

### Retrieval failure

Cau hoi ve thoi hieu xu phat nha xuat ban thuc hien xuat ban dien tu nhung chua duoc xac nhan dang ky. Ket qua retrieve dua cac doan noi dung hanh vi/muc phat len dau, trong khi gold la quy dinh ve thoi hieu o `cid=63171` va khong vao top-20.

**Bai hoc:** lexical/semantic relevance voi hanh vi khong dong nghia passage tra loi dung intent "thoi hieu". Huong cai tien gom intent-aware retrieval, document linkage giua dieu xu phat va dieu thoi hieu, hard negatives theo intent va multi-hop retrieval.

### Citation failure

Cau hoi ve co quan tham quyen theo Khoan 1 Dieu 53 Luat Ho tich duoc tra loi dung y "Co quan dai dien", nhung prediction khong co citation nen citation presence/correctness bang 0.

**Bai hoc:** answer correctness va citation correctness la hai truc rieng. Structured generation/constrained citation can duoc danh gia rieng voi noi dung answer.

## 6. Cac cau noi an toan khi trinh bay ket qua

Nen dung:

- "Trong run 300 mau hien tai, cross-encoder cai thien MRR tu 0,3859 len 0,4648."
- "Faithfulness 0,9408 la proxy dua tren evidence, khong phai 94,08% do dung phap ly."
- "Human evaluation cho tin hieu tich cuc ban dau, nhung annotator khong phai chuyen gia luat."
- "QA-memory audit khong tim thay exact duplicate, nhung van con hai near-duplicates va cac dang leakage khac can kiem tra."
- "RAFT la huong dang hoan thien, chua phai ket qua chinh cua he thong."

Tranh dung:

- "He thong chinh xac 94%."
- "RAG khong hallucinate."
- "Cross-encoder chac chan tot hon" ma khong noi sample size va thieu significance test.
- "Dense retrieval" cho char sparse branch ma khong giai thich implementation.
- "Da human validation" ma khong noi annotator khong phai legal experts.
- "He thong tu dong biet luat nao con hieu luc."

## 7. Rehearsal checklist

### Noi dung

- [ ] Noi duoc thong diep trung tam trong 30 giay.
- [ ] Ve va giai thich data flow trong 2 phut ma khong nhin code.
- [ ] Phan biet word sparse, char sparse, neural dense va cross-encoder.
- [ ] Giai thich duoc QA-memory khong phai answer cache.
- [ ] Nho bon con so retrieval: N=300, R@5 0,6133, R@20 0,7033, MRR 0,4648.
- [ ] Nho ba con so generation: N=200, QLoRA F1 0,5909, ROUGE-L 0,4808.
- [ ] Noi dung y nghia va gioi han cua faithfulness proxy 0,9408.
- [ ] Noi dung tinh trang RAFT, human evaluation va temporal validity.

### Demo

- [ ] `/health` tra ve thanh cong va mode dung voi dieu sap trinh bay.
- [ ] Success case tra ve evidence/citation co the mo va doi chieu.
- [ ] Refusal case da thu truoc; san sang coi failure la case study.
- [ ] Co JSON/anh fallback cho ca hai case.
- [ ] Tat notification, tang font va mo san UI/debug tab.

### Q&A

- [ ] Tra loi moi cau bang cau truc: ket luan -> bang chung -> han che/next step.
- [ ] Khong phong doan con so latency, VRAM hay legal accuracy khi repo chua benchmark.
- [ ] Neu chua co experiment, noi ro do la gia thuyet va mo ta experiment de kiem chung.
- [ ] Neu mentor chi ra sai lech label/metric, tach loi data, retrieval, generation va evaluation truoc khi tra loi.

## 8. Nguon doi chieu trong repo

- Kien truc va trang thai: `README.md`
- Serving/retrieval weights: `configs/serving/`
- QLoRA hyperparameters: `configs/training/runpod.qwen2_5_7b_qlora.json`
- Runtime pipeline: `src/qa/pipeline.py`
- Retrieval fusion: `src/retrieval/hybrid_retriever.py`
- Reranker va fallback: `src/reranker/cross_encoder_reranker.py`, `src/reranker/model_reranker.py`
- Prompt va output: `src/qa/prompt_builder.py`, `src/api/schemas.py`
- Ket qua va canh bao dien giai: `reports/paper_experiments.md`
- Human evaluation: `reports/human_eval_summary.md`
- Leakage: `reports/qa_memory_leakage_audit.md`

Neu tai lieu va runtime mau thuan, uu tien artifact/config/report cua dung run dang trinh bay va noi ro version. Dac biet, khong lap lai dong README cu rang cross-encoder chua ton tai: repo hien co artifact `models/reranker-best`, nhung mode live van phai xac nhan qua health/response.
