# Suggested Changes For The Synthetic Rental Agreement

This is a reference checklist for issue #426. The live E2E still verifies the
assistant output against the current laws collector/RAG corpus.

1. Monetary security/deposit
   - Old clause: landlord can set off the deposit at personal discretion and
     return the rest "sometime" after lease end.
   - Suggested change: state what the deposit secures, when deductions are
     allowed, how they are documented, and when the remaining amount is returned.
   - Law grounding to verify live: Slovak Civil Code rental provisions and, if
     the agreement is treated as short-term apartment lease, Act No. 98/2014 Z. z.

2. Handover protocol and meter readings
   - Old clause: no handover protocol or meter state is needed.
   - Suggested change: require a written handover protocol with apartment
     condition, keys, equipment, meter readings, and photo/documentation annexes.
   - Law grounding to verify live: Slovak Civil Code duties around lease object
     handover/use and short-term apartment lease transparency requirements where applicable.

3. Repairs, defects, and damage
   - Old clause: tenant pays all repairs regardless of cause or amount.
   - Suggested change: separate ordinary minor maintenance, tenant-caused damage,
     landlord duties for defects not caused by the tenant, and notice duties.
   - Law grounding to verify live: Slovak Civil Code lease provisions on use,
     defects, maintenance, and liability.

4. Termination and notice delivery
   - Old clause: landlord can terminate anytime without reason, seven-day notice,
     including oral/SMS notice.
   - Suggested change: define written termination, lawful grounds, notice period,
     delivery method, and evidence of delivery.
   - Law grounding to verify live: Slovak Civil Code apartment-rental termination
     provisions and Act No. 98/2014 Z. z. if the short-term lease regime applies.

5. Delivery of documents
   - Old clause: documents are deemed delivered merely by sending to phone/email.
   - Suggested change: use written/electronic delivery with provable receipt or
     legally supportable substitute delivery wording.
   - Law grounding to verify live: Slovak Civil Code legal-act/delivery principles
     plus the selected lease regime.

6. Current-law clause
   - Old clause: agreement is governed by law as of 1 January 2000.
   - Suggested change: agreement is governed by the law of the Slovak Republic
     effective at signing/performance, with mandatory provisions prevailing.

Human oversight: This checklist is for synthetic test validation. The generated
agreement must remain a draft for human/legal review before real use.
