# Text-to-SQL Metrics Reference

สรุป metrics ที่นิยมใช้ในการประเมินระบบ Text-to-SQL สำหรับงานวิจัย งานทดลองโมเดล และงานเชิงโปรดักชัน โดยเรียงในรูปแบบ: ชื่อ metric, วัดอะไร, ค่าที่ได้บอกอะไร, และวัดยังไง [web:13][web:50]

## หมายเหตุเบื้องต้น

- ไม่มี metric ตัวเดียวที่ครอบคลุมทุกมิติของ Text-to-SQL ได้ครบทั้งหมด เพราะบางตัวเน้นความเหมือนของ SQL, บางตัวเน้นผลลัพธ์ที่ execute ได้จริง, และบางตัวเน้นความหมายหรือความทนทานของ query [web:13][web:23][web:61]
- ถ้าทำงานวิจัย ควรระบุ definition ของ metric ให้ชัด เพราะชื่อคล้ายกันอาจมี implementation ต่างกันได้ในแต่ละ benchmark หรือแต่ละ paper [web:13][web:23]

---

## 1) Exact Match (EM)

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดว่าคำสั่ง SQL ที่โมเดลสร้าง ตรงกับ SQL เฉลยแบบเป๊ะหรือไม่ในเชิงโครงสร้าง/ข้อความหลังการ normalize ตามกติกาของ benchmark [web:13][web:23]  
ค่าที่ได้มักเป็น 0 หรือ 1 ต่อหนึ่งตัวอย่าง และเมื่อเฉลี่ยทั้งชุดทดสอบจะได้เป็น accuracy; คะแนนสูงหมายถึงโมเดลสร้าง SQL ได้เหมือนเฉลยมาก แต่ไม่ได้แปลว่าความหมายถูกเสมอไปถ้ามีหลาย query ที่ให้ผลลัพธ์เท่ากัน [web:23][web:61]

**วัดยังไง :**  
นำ SQL prediction ไปเทียบกับ ground-truth SQL โดยใช้ตัวเปรียบเทียบของ benchmark ซึ่งอาจ normalize alias, ลำดับบางส่วน, หรือ representation ภายในก่อนเทียบ [web:13][web:23]  
ถ้าตรงทั้งหมดให้นับว่าถูก, ถ้าไม่ตรงให้นับว่าผิด [web:23]

---

## 2) Component Matching / Clause-level Match

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความถูกต้องแยกตามองค์ประกอบของ SQL เช่น `SELECT`, `WHERE`, `GROUP BY`, `ORDER BY`, `JOIN`, `HAVING`, และ nested query [web:65][web:13]  
ค่าที่ได้ช่วยบอกว่าโมเดลพลาดตรงส่วนไหน เช่น เลือกคอลัมน์ถูกแต่เงื่อนไขกรองผิด หรือ join relation ผิด [web:65]

**วัดยังไง :**  
แยก SQL ทั้ง prediction และ ground truth ออกเป็น clause หรือ component ย่อย แล้วเทียบทีละส่วน [web:65]  
จากนั้นรายงานเป็น accuracy รายส่วน หรือสรุปรวมในลักษณะ partial exact match [web:65][web:13]

---

## 3) Partial Match Accuracy (PM)

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความถูกต้องแบบไม่ตัดสินขาวดำทั้ง query แต่ดูว่าถูกบางส่วนมากน้อยแค่ไหน [web:36][web:74]  
ค่าที่ได้ช่วยสะท้อน progress ของโมเดลในกรณีที่ query ซับซ้อนมากและผิดเพียงบางองค์ประกอบ ไม่ใช่ผิดทั้งหมด [web:36][web:74]

**วัดยังไง :**  
คำนวณจากจำนวนส่วนของ SQL ที่ตรงกับเฉลย เช่น clause, operator, column, table, หรือ logical unit ที่ตรงกัน [web:36][web:74]  
บางงานจะสรุปเป็นสัดส่วนระหว่าง 0 ถึง 1 แทนการให้ผ่าน/ไม่ผ่านแบบ binary [web:74]

---

## 4) Execution Accuracy (EX)

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดว่ารัน SQL แล้วได้ผลลัพธ์ตรงกับเฉลยหรือไม่ [web:23][web:61]  
ค่าที่ได้บอกว่า query ของโมเดลใช้งานได้จริงในเชิง semantic มากกว่า EM เพราะไม่ยึดติดว่าต้องเขียนเหมือนเฉลยทุกตัวอักษร [web:23][web:59]

**วัดยังไง :**  
นำ SQL prediction ไปรันบนฐานข้อมูลจริง แล้วเปรียบเทียบ result set กับ result set ของ SQL เฉลย [web:23][web:59]  
ถ้าผลลัพธ์ตรงกันให้นับว่าถูก แม้ SQL จะมีรูปแบบต่างจากเฉลย [web:23][web:59]

---

## 5) Execution Match Rate / Result-set Match

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
เป็นกลุ่ม metric ที่ดูความตรงกันของผลลัพธ์หลัง execute เช่น ตารางที่ได้, ค่า aggregate, หรือ row set ที่ดึงกลับมา [web:23][web:61]  
ค่าที่ได้เหมาะกับ use case ที่สนผลลัพธ์ธุรกิจมากกว่าหน้าตา SQL [web:23]

**วัดยังไง :**  
เปรียบเทียบผลลัพธ์จาก query prediction กับผลลัพธ์อ้างอิง โดยอาจ normalize ลำดับแถว, duplicate handling, หรือ type casting ตามกติกาของระบบประเมิน [web:23][web:61]

---

## 6) Test Suite Accuracy (TSA / TS)

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความถูกต้องเชิงความหมายของ SQL อย่างเข้มขึ้น โดยลดปัญหาที่ EX อาจให้ผ่านเพราะข้อมูลในฐานนั้นดันทำให้ query ผิดแต่ได้ผลตรงโดยบังเอิญ [web:58][web:13]  
ค่าที่ได้บอกว่า query มี semantic equivalence กับเฉลยดีแค่ไหนเมื่อทดสอบกับหลายฐานข้อมูลย่อยหรือหลายกรณีข้อมูล [web:58]

**วัดยังไง :**  
สร้างหรือใช้ชุดฐานข้อมูลทดสอบหลายแบบสำหรับ query เดียวกัน แล้วรันทั้ง prediction และ reference บนทุกชุด [web:58]  
จะนับว่าถูกก็ต่อเมื่อผลลัพธ์สอดคล้องกับเฉลยใน test suites ทั้งหมดตามเกณฑ์ของ benchmark [web:58]

---

## 7) Fractional Execution Accuracy / Partial Execution Reward

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความถูกต้องของผลลัพธ์แบบเป็นสัดส่วน ไม่ใช่ถูกหรือผิดทั้งก้อน [web:74]  
ค่าที่ได้บอกว่า query ดึงผลลัพธ์ได้ใกล้เคียงเฉลยแค่ไหน เช่น ถูกบางคอลัมน์หรือบางส่วนของผลลัพธ์ [web:74]

**วัดยังไง :**  
ให้คะแนนตามระดับความ overlap ระหว่างผลลัพธ์ของ prediction กับผลลัพธ์อ้างอิง แทนการตัดสินแบบ binary [web:74]  
เหมาะกับงานฝึกโมเดลหรือ reinforcement learning ที่ต้องการ reward ที่ละเอียดกว่า EX [web:36][web:74]

---

## 8) SQL Validity Rate

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดว่า SQL ที่โมเดลสร้างมีรูปแบบถูกต้องตามไวยากรณ์และพร้อมรันหรือไม่ [web:23][web:67]  
ค่าที่ได้บอกถึงความสามารถขั้นพื้นฐานของโมเดลในการสร้าง query ที่ไม่พังตั้งแต่ระดับ syntax [web:23]

**วัดยังไง :**  
ส่ง query ไป parse หรือ execute กับ database engine แล้วดูว่าเกิด syntax error หรือ parser error หรือไม่ [web:23][web:67]  
ถ้า parse ผ่านหรือ execute ได้อย่างน้อยในระดับ syntax ก็ถือว่า valid [web:23]

---

## 9) Executability Rate

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดว่า query สามารถ execute ได้จริงโดยไม่ล้มจาก runtime error เช่น table ไม่เจอ, column ไม่เจอ, type ไม่ตรง, หรือ function ใช้ผิด dialect [web:23][web:67]  
ค่าที่ได้บอกว่าโมเดลเชื่อมโยง schema และ dialect ได้ดีพอสำหรับการใช้งานจริงหรือยัง [web:23][web:67]

**วัดยังไง :**  
นำ query ไปรันบนระบบฐานข้อมูลจริงหรือ environment จำลอง แล้วเช็กว่า run สำเร็จหรือไม่ [web:23]  
ต่างจาก validity ตรงที่ executability สนใจ runtime success มากกว่า parse success อย่างเดียว [web:23][web:67]

---

## 10) Schema Linking Accuracy

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความสามารถของโมเดลในการเชื่อมคำในคำถามธรรมชาติกับ table, column, foreign key, หรือ value ใน schema [web:68][web:13]  
ค่าที่ได้บอกว่าโมเดลเข้าใจฐานข้อมูลถูกจุดหรือไม่ ซึ่งมักเป็นต้นเหตุหลักของ query ผิด [web:68]

**วัดยังไง :**  
เทียบว่าชุด schema items ที่โมเดลเลือกใช้นั้นตรงกับ gold schema links หรือองค์ประกอบที่ควรถูกอ้างถึงหรือไม่ [web:68]  
มักรายงานเป็น precision, recall, หรือ F1 [web:68]

---

## 11) Table Prediction Accuracy

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดว่าโมเดลเลือกตารางที่เกี่ยวข้องกับคำถามถูกหรือไม่ [web:68][web:65]  
ค่าที่ได้ช่วยบอกปัญหาเรื่อง table selection โดยเฉพาะในฐานข้อมูลที่มีหลายตาราง [web:68]

**วัดยังไง :**  
นำชุด tables ที่ปรากฏใน prediction ไปเทียบกับชุด tables ใน query อ้างอิง [web:65][web:68]  
รายงานเป็น exact accuracy หรือ precision/recall/F1 ก็ได้ [web:65]

---

## 12) Column Prediction Accuracy

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดว่าโมเดลเลือกคอลัมน์ที่ถูกต้องสำหรับ `SELECT`, `WHERE`, `GROUP BY`, `ORDER BY` และเงื่อนไขอื่นหรือไม่ [web:65][web:68]  
ค่าที่ได้บอกปัญหาเรื่อง semantic grounding ระดับละเอียด เพราะหลายครั้งเลือก table ถูกแต่ column ผิด [web:65]

**วัดยังไง :**  
เทียบชุด columns ที่ prediction ใช้กับ columns ใน SQL เฉลย หรือใน gold annotation ของ schema linking [web:65][web:68]  
อาจวัดแยกตาม clause เพื่อเห็น error pattern ชัดขึ้น [web:65]

---

## 13) Join Accuracy

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดว่าโมเดลเชื่อมตารางถูกคู่และถูกเงื่อนไขหรือไม่ [web:13][web:65]  
ค่าที่ได้บอกถึงความสามารถในการเข้าใจ relational structure ของฐานข้อมูล ซึ่งสำคัญมากใน benchmark แบบ cross-domain [web:13]

**วัดยังไง :**  
เทียบ join path, join condition, หรือชุดความสัมพันธ์ที่ใช้ใน prediction กับเฉลย [web:65][web:13]  
บางงานนับ join เป็น component หนึ่งใน clause-level evaluation [web:65]

---

## 14) Condition Accuracy

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความถูกต้องของเงื่อนไขกรอง เช่น operator (`=`, `>`, `LIKE`), value, logical connector (`AND`/`OR`) และช่วงข้อมูล [web:65][web:13]  
ค่าที่ได้บอกว่าโมเดลเข้าใจข้อจำกัดและ intent ของผู้ใช้ลึกแค่ไหน [web:65]

**วัดยังไง :**  
แตกส่วน `WHERE` หรือ `HAVING` ออกมา แล้วเทียบ field, operator, และ value กับเฉลย [web:65]  
อาจให้คะแนนแบบ exact หรือ partial ตามองค์ประกอบที่ตรง [web:65]

---

## 15) Aggregation Accuracy

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดว่าโมเดลเลือก aggregation function ได้ถูกหรือไม่ เช่น `COUNT`, `SUM`, `AVG`, `MAX`, `MIN` [web:13][web:65]  
ค่าที่ได้บอกว่าโมเดลเข้าใจเจตนาคำถามเชิงสรุปผลถูกต้องหรือไม่ [web:13]

**วัดยังไง :**  
ตรวจว่า function ที่ prediction ใช้ตรงกับ function ใน query เฉลย และใช้กับ column ถูกตัวหรือไม่ [web:65]  
อาจรวมอยู่ใน component matching หรือรายงานแยกก็ได้ [web:65]

---

## 16) Value Prediction Accuracy

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดว่าโมเดลใส่ literal values, constants, หรือ parameter ใน query ได้ถูกต้องหรือไม่ [web:68][web:13]  
ค่าที่ได้บอกว่าโมเดลดึงเงื่อนไขจากคำถามมาใส่ใน SQL ได้ครบและแม่นแค่ไหน [web:68]

**วัดยังไง :**  
เทียบ values ที่ปรากฏใน prediction กับ values ที่ควรอยู่ใน query อ้างอิง [web:68]  
บางระบบแยกวัด exact value match และ normalized value match [web:68]

---

## 17) Precision

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดสัดส่วนขององค์ประกอบที่โมเดลทำนายว่าเกี่ยวข้อง แล้วถูกจริง [web:68][web:61]  
ค่าที่สูงหมายถึงโมเดลไม่ใส่ table, column, หรือ condition เกินจำเป็นมากนัก [web:61]

**วัดยังไง :**  
คำนวณจาก  
`Precision = TP / (TP + FP)` [web:61]  
โดยนิยาม TP/FP ตามระดับที่ประเมิน เช่น schema item, token, clause หรือ result item [web:61][web:68]

---

## 18) Recall

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดสัดส่วนขององค์ประกอบที่ควรมี แล้วโมเดลทำนายเจอจริง [web:61][web:68]  
ค่าที่สูงหมายถึงโมเดลไม่พลาดองค์ประกอบสำคัญของ query [web:61]

**วัดยังไง :**  
คำนวณจาก  
`Recall = TP / (TP + FN)` [web:61]  
โดยใช้กับ schema linking, component detection, หรือ result overlap ได้ [web:61][web:68]

---

## 19) F1-score

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความสมดุลระหว่าง precision และ recall [web:61]  
ค่าที่ได้บอกว่าโมเดลทั้งไม่ใส่เกินและไม่ตกหล่นมากเกินไป เหมาะกับงานประเมินระดับองค์ประกอบย่อย [web:61][web:68]

**วัดยังไง :**  
คำนวณจาก  
`F1 = 2 * Precision * Recall / (Precision + Recall)` [web:61]  
มักใช้กับ schema linking, token overlap, หรือ component-level evaluation [web:61][web:68]

---

## 20) Token-level Accuracy

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความถูกต้องระดับ token ของ SQL ที่สร้าง [web:61][web:13]  
ค่าที่ได้เหมาะกับการวิเคราะห์เชิงภาษาหรือใช้ระหว่างฝึกโมเดล แต่ไม่ได้สะท้อน semantic correctness ได้ดีเท่า EX หรือ TS [web:13][web:61]

**วัดยังไง :**  
แยก query ออกเป็น token แล้วเทียบกับ token sequence ของเฉลย [web:61]  
อาจนับเป็น accuracy ธรรมดา, precision/recall/F1, หรือ edit-based score [web:61]

---

## 21) Logical Form Accuracy

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดว่ารูปแบบเชิงตรรกะของ query ตรงกับเฉลยหรือไม่ โดยอาจไม่ยึดติดกับผิวหน้าของข้อความ SQL [web:13][web:3]  
ค่าที่ได้บอกว่าโมเดลจับความสัมพันธ์เชิงเหตุผลของ query ได้ถูกต้องมากน้อยเพียงใด [web:3]

**วัดยังไง :**  
แปลง SQL เป็น representation ภายใน เช่น normalized structure หรือ tree แล้วเทียบระดับ logical form [web:3][web:13]  
วิธีนี้ใช้เพื่อลดผลกระทบจาก formatting หรือการเขียนหลายแบบที่เทียบเท่ากัน [web:3]

---

## 22) Tree Match / AST Match

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความเหมือนของโครงสร้างต้นไม้ไวยากรณ์ของ SQL prediction กับเฉลย [web:3][web:13]  
ค่าที่ได้บอกว่าโครงสร้างการคำนวณโดยรวมตรงกันหรือไม่ แม้ข้อความ SQL จะต่างกัน [web:3]

**วัดยังไง :**  
parse SQL ทั้งสองฝั่งให้เป็น Abstract Syntax Tree (AST) แล้วเปรียบเทียบ node, edge หรือ subtree ที่สอดคล้องกัน [web:3]  
เหมาะกับงานที่ต้องการดู structural similarity ลึกกว่า exact string matching [web:3]

---

## 23) Enhanced Tree Matching (ETM)

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
เป็น metric ที่เสนอเพื่อสะท้อน semantic และ structural similarity ของ SQL ได้ดีกว่า EM/EX แบบดั้งเดิม [web:3][web:13]  
ค่าที่ได้บอกว่า prediction ใกล้เคียง query อ้างอิงแค่ไหนในเชิงโครงสร้างและความหมาย พร้อมลดข้อผิดพลาดจากการตัดสินแบบหยาบ [web:3]

**วัดยังไง :**  
แปลง query เป็น tree representation ที่ normalize ความแตกต่างที่เทียบเท่ากัน แล้วคำนวณความใกล้เคียงระหว่างต้นไม้ [web:3]  
บางงานรายงานคะแนนเป็น continuous score มากกว่า pass/fail [web:3]

---

## 24) Semantic Similarity Score

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความใกล้เคียงเชิงความหมายระหว่าง query prediction กับ query อ้างอิง [web:3][web:79]  
ค่าที่ได้ช่วยตอบโจทย์ว่าแม้ SQL จะเขียนไม่เหมือนกัน แต่มี intent เดียวกันหรือไม่ [web:3]

**วัดยังไง :**  
อาจอาศัยการเปรียบเทียบที่ semantic-aware เช่น execution-based evidence, tree representation, หรือ LLM-as-judge framework [web:3][web:79]  
implementation ต่างกันตามงานวิจัยและ benchmark [web:13][web:79]

---

## 25) Structural Similarity Score

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความคล้ายเชิงโครงสร้างของ query เช่น clause arrangement, nested blocks, join graph หรือ computation pattern [web:3]  
ค่าที่ได้เหมาะกับงานที่อยากแยก “เขียน structure ถูกไหม” ออกจาก “ได้ผลลัพธ์ถูกไหม” [web:3]

**วัดยังไง :**  
ใช้ representation เชิงโครงสร้าง เช่น AST หรือ canonical query graph แล้วคำนวณ similarity [web:3]  
มักใช้คู่กับ semantic score เพื่อให้เห็นทั้งสองด้าน [web:3]

---

## 26) FLEX (False-Less EXecution)

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความถูกต้องเชิงความหมายโดยพยายามลด false positives และ false negatives ที่เกิดจาก EX ปกติ [web:11][web:79]  
ค่าที่ได้บอกว่า query ของโมเดลถูกต้องตาม intent ของคำถามมากน้อยเพียงใด เมื่อดูทั้ง query, schema และผลลัพธ์ร่วมกัน [web:11]

**วัดยังไง :**  
ใช้ตัวประเมินที่มี reasoning capability สูงเข้ามาตัดสิน โดยดูคำถาม, schema, SQL เฉลย, SQL prediction และผล execute ประกอบกัน [web:11][web:79]  
แนวคิดคือไม่ตัดสินจาก result equality อย่างเดียว แต่ดูความหมายโดยรวมของ query ด้วย [web:11]

---

## 27) Consistency

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความสม่ำเสมอของโมเดลเมื่อถามซ้ำ ปรับ prompt เล็กน้อย หรือสุ่มหลายรอบ [web:51][web:54]  
ค่าที่ได้บอกว่าโมเดลมีเสถียรภาพพอสำหรับใช้งานจริงหรือไม่ เพราะ Text-to-SQL โดยเฉพาะ LLM อาจตอบต่างกันในคำถามเดียวกัน [web:51]

**วัดยังไง :**  
รันโมเดลหลายครั้งกับ input เดิมหรือ input paraphrase แล้ววัดสัดส่วนที่ให้คำตอบถูกเหมือนเดิม [web:51][web:54]  
อาจสรุปเป็น self-consistency accuracy หรือ variance ของผลลัพธ์ [web:51]

---

## 28) Robustness Score

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความทนทานของโมเดลต่อการเปลี่ยนแปลงเล็กน้อย เช่น paraphrase, schema alias, data model variation หรือ ambiguity [web:18][web:69]  
ค่าที่ได้บอกว่าโมเดล generalize ได้ดีแค่ไหนนอกเหนือจาก test set ปกติ [web:18]

**วัดยังไง :**  
สร้างชุดทดสอบที่ perturb คำถามหรือ schema แล้ววัดว่าคะแนนหลักอย่าง EX/EM ลดลงเท่าไร [web:18][web:69]  
คะแนน robustness อาจรายงานเป็น absolute score หรือ performance drop [web:18]

---

## 29) Ambiguity Handling Score

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความสามารถของระบบในการจัดการคำถามที่กำกวม ซึ่งอาจมีหลาย SQL ที่สมเหตุสมผล [web:69]  
ค่าที่ได้บอกว่าโมเดลแยกแยะ ambiguity หรือขอข้อมูลเพิ่มได้ดีเพียงใด [web:69]

**วัดยังไง :**  
ใช้ชุด benchmark ที่ออกแบบมาสำหรับ ambiguous queries แล้ววัดว่าระบบให้ query ที่สอดคล้องกับ interpretation ที่ถูกต้องหรือจัดการ ambiguity อย่างเหมาะสมหรือไม่ [web:69]

---

## 30) Query Latency

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดเวลาที่ใช้ในการ generate SQL หรือ execute SQL แล้วแต่บริบทการประเมิน [web:23][web:67]  
ค่าที่ได้บอกความเหมาะสมสำหรับงาน real-time หรือระบบโต้ตอบกับผู้ใช้ [web:23]

**วัดยังไง :**  
จับเวลา end-to-end ตั้งแต่รับคำถามจนได้ SQL หรือจนได้ผลลัพธ์จากฐานข้อมูล [web:23][web:67]  
อาจรายงานเป็น average latency, p95 latency หรือ latency แยกแต่ละขั้น [web:23]

---

## 31) Valid Efficiency Score (VES)

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดทั้งความถูกต้องของ query และประสิทธิภาพในการ execute [web:19][web:20]  
ค่าที่ได้บอกว่าโมเดลไม่เพียงตอบถูก แต่ยังเขียน query ได้มีประสิทธิภาพพอสำหรับฐานข้อมูลขนาดใหญ่ [web:19]

**วัดยังไง :**  
ให้คะแนนเฉพาะ query ที่ execute ได้ถูกต้องก่อน แล้วพิจารณาเวลา execute หรือ resource usage เทียบกับ baseline/ground truth [web:19][web:20]  
เหมาะกับ benchmark ที่สนใจ production realism เช่นฐานข้อมูลขนาดใหญ่ [web:19]

---

## 32) Resource Cost / Compute Cost

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดต้นทุนเชิงทรัพยากรของระบบ เช่น token cost, inference cost, memory หรือ compute footprint ระหว่าง generate และ evaluate [web:20][web:50]  
ค่าที่ได้บอกความคุ้มค่าต่อการใช้งานจริง โดยเฉพาะระบบที่ต้อง serve ผู้ใช้จำนวนมาก [web:20]

**วัดยังไง :**  
บันทึกจำนวน token, latency, GPU/CPU usage หรือค่าใช้จ่ายต่อ query แล้วสรุปเป็นค่าเฉลี่ยต่อเคส [web:20][web:50]

---

## 33) Success Rate under Dialect Constraints

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดว่าระบบสร้าง SQL ที่สอดคล้องกับ dialect เป้าหมาย เช่น SQLite, PostgreSQL, MySQL, BigQuery หรือ Snowflake ได้ดีแค่ไหน [web:20][web:67]  
ค่าที่ได้บอกความพร้อมสำหรับการ deploy กับ database engine จริง [web:20]

**วัดยังไง :**  
รัน query บน engine เป้าหมายหรือ parser ของ dialect นั้น แล้ววัด validity/executability/execution accuracy ภายใต้ dialect constraints [web:20][web:67]

---

## 34) Business Answer Accuracy

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดว่าคำตอบสุดท้ายที่ผู้ใช้ต้องการจากระบบ BI หรือ analytics ถูกต้องหรือไม่ แม้ SQL ภายในจะไม่ได้ตรงกับเฉลยเป๊ะ [web:22][web:23]  
ค่าที่ได้บอกคุณภาพในมุมผู้ใช้ปลายทางมากกว่ามุม parser research [web:22]

**วัดยังไง :**  
เปรียบเทียบคำตอบสุดท้ายที่ผู้ใช้เห็น เช่น numeric answer, ranked list, หรือ summary table กับ expected business output [web:22][web:23]  
เหมาะกับระบบถามข้อมูลเชิงธุรกิจมากกว่างาน benchmark วิชาการล้วน [web:22]

---

## 35) Human Evaluation

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดคุณภาพของ query หรือคำตอบผ่านผู้ประเมินมนุษย์ เช่น ความถูกต้อง, ความเข้าใจง่าย, ความเป็นประโยชน์, หรือความน่าเชื่อถือ [web:11][web:20]  
ค่าที่ได้บอกมิติที่ metric อัตโนมัติอาจวัดไม่ครบ เช่น ความเหมาะสมเชิงบริบทหรือการยอมรับได้ของ query [web:11]

**วัดยังไง :**  
ให้ผู้เชี่ยวชาญหรือ annotator ตรวจ prediction แล้วให้ label หรือ score ตาม rubric ที่กำหนด [web:11][web:20]  
มักใช้เป็น gold check สำหรับ validate metric อัตโนมัติใหม่ๆ [web:11]

---

## 36) LLM-as-a-Judge Score

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดคุณภาพ prediction ผ่านโมเดลผู้ตัดสินที่พิจารณาคำถาม, schema, SQL และบางครั้งผลลัพธ์การรันร่วมกัน [web:11][web:79]  
ค่าที่ได้บอกการสอดคล้องเชิง semantic ในกรณีที่ exact หรือ execution-based metric ไม่พอ [web:11]

**วัดยังไง :**  
ออกแบบ prompt ให้ evaluator model ตัดสินว่าคำตอบถูกหรือไม่ หรือให้คะแนนหลายระดับ [web:11][web:79]  
ต้องระวังเรื่อง bias และควรมี human validation รองรับ [web:11]

---

## 37) Error Category Distribution

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดการกระจายประเภทข้อผิดพลาด เช่น schema linking error, join error, aggregation error, value error, ambiguity error [web:18][web:69]  
ค่าที่ได้ไม่ได้เป็น “accuracy” โดยตรง แต่ช่วยบอกจุดอ่อนของโมเดลชัดมากสำหรับงานวิเคราะห์และปรับปรุงระบบ [web:18]

**วัดยังไง :**  
ทำ error annotation ให้กับ prediction ที่ผิด แล้วสรุปสัดส่วนแต่ละประเภท [web:18][web:69]  
มักใช้คู่กับ EM/EX เพื่ออธิบายผลการทดลอง [web:18]

---

## 38) Cross-domain Generalization Score

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความสามารถของโมเดลในการทำงานกับ schema หรือโดเมนที่ไม่เคยเห็นมาก่อน [web:18][web:48]  
ค่าที่ได้บอกว่าโมเดลเรียนรู้หลักการของ Text-to-SQL จริง หรือแค่จำรูปแบบจาก training set [web:18]

**วัดยังไง :**  
ประเมินบน benchmark ที่ train/test อยู่คนละ database หรือคนละ domain แล้วใช้ metric หลักอย่าง EM, EX, หรือ TS เป็นตัวรายงาน [web:18][web:48]  
ตัว score นี้จึงเป็นมุมมองของการจัดชุดทดสอบมากกว่าจะเป็นสูตรคำนวณใหม่ [web:18]

---

## 39) Reliability / Trustworthiness Score

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความน่าเชื่อถือของระบบเมื่อใช้งานจริง เช่น การหลีกเลี่ยง query อันตราย, ความสม่ำเสมอ, ความปลอดภัย หรือการปฏิเสธคำขอไม่เหมาะสม [web:16][web:20]  
ค่าที่ได้บอกว่าระบบเหมาะกับ production มากน้อยเพียงใด ไม่ใช่แค่ตอบ benchmark ได้ดี [web:16]

**วัดยังไง :**  
ใช้กรอบประเมินแบบ penalty-based หรือ scenario-based ที่รวมหลายเงื่อนไข เช่น correctness, harmlessness และ operational reliability [web:16]  
metric กลุ่มนี้กำลังได้รับความสนใจมากขึ้นในยุค LLM [web:16][web:20]

---

## 40) Safety Violation Rate

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดสัดส่วนของ query ที่ละเมิดข้อจำกัดด้านความปลอดภัย เช่น สร้างคำสั่งแก้ไขข้อมูล, ลบตาราง, หรือเข้าถึงข้อมูลที่ไม่ควรแตะ [web:16][web:20]  
ค่าที่ต่ำหมายถึงระบบปลอดภัยกว่าในการใช้งานจริง [web:16]

**วัดยังไง :**  
เตรียมชุดคำถามหรือสถานการณ์ที่ต้องตรวจจับ query อันตราย แล้ววัดว่าระบบหลีกเลี่ยงหรือปฏิเสธได้กี่ครั้ง [web:16][web:20]  
แม้จะยังไม่ใช่ metric มาตรฐานสากลเท่า EM/EX แต่สำคัญมากใน production [web:20]

---

## 41) Calibration / Confidence Quality

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดว่าความมั่นใจของโมเดลสอดคล้องกับความถูกต้องจริงหรือไม่ [web:20][web:50]  
ค่าที่ได้ช่วยให้ระบบตัดสินใจได้ว่าจะตอบเลย, ขอ clarification, หรือส่งต่อให้มนุษย์ตรวจ [web:20]

**วัดยังไง :**  
ใช้ confidence score ของโมเดลหรือ self-evaluation แล้วเปรียบเทียบกับ outcome จริง เช่น accuracy bucket หรือ calibration error [web:20][web:50]

---

## 42) End-to-End Task Success

**วัดอะไร และค่าที่ได้ออกมาบอกอะไร :**  
วัดความสำเร็จของระบบตั้งแต่รับคำถามจนส่งคำตอบใช้งานได้จริง รวมหลายขั้นตอนเข้าด้วยกัน เช่น schema retrieval, SQL generation, execution และ answer presentation [web:22][web:20]  
ค่าที่ได้บอกประสิทธิภาพจริงของระบบมากกว่าคะแนน parser ล้วน [web:22]

**วัดยังไง :**  
กำหนดว่าเคสหนึ่งจะ “สำเร็จ” เมื่อทุกขั้นจำเป็นผ่านเกณฑ์ เช่น SQL รันได้, ได้คำตอบถูก, อยู่ใน latency ที่รับได้, และไม่ละเมิด policy [web:22][web:20]

---

## แนะนำการเลือกใช้แบบเร็ว

- ถ้าต้องการมาตรฐานงานวิจัยพื้นฐาน: ใช้ `EM + EX + TSA` [web:13][web:58]
- ถ้าทำระบบใช้งานจริง: เพิ่ม `SQL Validity`, `Executability`, `Latency`, `VES`, และ `Safety Violation Rate` [web:20][web:23][web:16]
- ถ้าต้องการวิเคราะห์ข้อผิดพลาดเชิงลึก: เพิ่ม `Component Matching`, `Schema Linking Accuracy`, `Join Accuracy`, `Value Prediction Accuracy`, และ `Error Category Distribution` [web:65][web:68][web:18]
- ถ้าสนใจ semantic evaluation สมัยใหม่: ดู `ETM`, `FLEX`, และกลุ่ม `Semantic/Structural Similarity` เพิ่มเติม [web:3][web:11][web:79]

## อ้างอิงหลักที่ควรอ่าน

- ETM และแนวคิด metric สมัยใหม่สำหรับ Text-to-SQL [web:3][web:13]
- Semantic Evaluation for Text-to-SQL with Distilled Test Suites [web:58]
- FLEX: Expert-level False-Less EXecution Metric for Reliable Text-to-SQL Benchmark [web:11][web:79]
- งาน survey และ benchmark analysis ของ Text-to-SQL ในยุค LLM [web:18][web:20][web:50]
