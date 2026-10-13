INSERT OR REPLACE INTO failure_modes (code, name, fmea_row) VALUES
 ('FM01','Catheter body break','2. Line breaks'),
 ('FM02','External component failure','5. Cap or clamp fails'),
 ('FM03','Occlusion','7. Resistance when drawing or infusing'),
 ('FM04','Kink / deformation',NULL),
 ('FM05','Insertion accessory failure',NULL),
 ('FM06','Malposition / migration',NULL),
 ('FM07','Difficult insertion / removal',NULL),
 ('FM08','Packaging / assembly defect before use','1. Not sterile; 4. Re-used'),
 ('FM09','Infection','1, 4, 8 (consequence)'),
 ('FM10','Thrombosis','6. Thrombosis'),
 ('FM11','Vessel injury / extravasation',NULL),
 ('FM12','Other / insufficient information',NULL),
 ('FM13','Tissue / hypersensitivity reaction','3. Rejected by the body');

INSERT OR REPLACE INTO keyword_watchlist (term_group, pattern) VALUES
 ('septum_leak','%STOPPER%'), ('septum_leak','%SEPTUM%'), ('septum_leak','%T-LOCK%'),
 ('septum_leak','%T LOCK%'),  ('septum_leak','%RUBBER PIECE%'),
 ('air_entry','%AIR ENTER%'), ('air_entry','%SUCKS AIR%'), ('air_entry','%AIR GETS PULLED%'),
 ('air_entry','%ENTRAINS AIR%'), ('air_entry','%AIR EMBOL%'),
 ('fragment_retained','%REMAINED IN%'), ('fragment_retained','%LEFT IN%'),
 ('fragment_retained','%FOREIGN BODY%'), ('fragment_retained','%SNARE%');
