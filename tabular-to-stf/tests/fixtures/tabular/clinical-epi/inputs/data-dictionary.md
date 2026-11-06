# Data dictionary: Lake Victoria household malaria survey

villages.csv
- village_id: village code
- name: village name
- lat, lon: village centre, WGS-84 decimal degrees
- Long-standing market: village has had a weekly market for 10+ years (Yes/No)

households.csv
- household_id: household code
- village_id: village code
- construction material: main wall material
- number of rooms: rooms used for sleeping
- roof type: main roof material

participants.csv
- participant_id: participant code
- household_id: household code
- Participant name: full name (confidential)
- Sex: Female/Male
- Age (years): age at enrolment in completed years; ages of 80 and over recorded as 80+
- Bednet use: slept under a bednet the previous night
- Enrolment date: DD/MM/YYYY
- Weight (kg), Height (cm): measured at enrolment
- Education level: highest level completed (none, primary, secondary, tertiary)
- Occupation: main occupation
- Fever last 14 days: self-reported fever in the 14 days before enrolment

samples.csv
- sample_id: sample code
- participant_id: participant code
- collection date: YYYY-MM-DD
- Temperature (°C): axillary temperature
- Hb (g/dL): haemoglobin by HemoCue
- Malaria RDT result: Positive/Negative
