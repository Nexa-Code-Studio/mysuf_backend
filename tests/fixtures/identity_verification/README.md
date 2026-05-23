# Identity Verification Fixtures

This directory is reserved for stable sample images used by OCR and face verification tests.

Recommended fixture set:

- `ktp_clear.jpg`: KTP fully visible, sharp, readable NIK
- `ktp_blurry.jpg`: KTP blurred enough to trigger quality rejection
- `ktp_glare.jpg`: KTP with strong reflection over text or portrait area
- `selfie_valid.jpg`: one clear face, centered, good lighting
- `selfie_multi_face.jpg`: two visible faces to trigger multi-face rejection
- `selfie_mismatch.jpg`: valid selfie but different identity than KTP portrait

Current automated tests use generated or mocked inputs so the suite stays lightweight and deterministic.
When real fixtures are added, keep them small, anonymized, and safe for source control.
