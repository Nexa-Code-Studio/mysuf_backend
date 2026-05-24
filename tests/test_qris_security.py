import base64
import pytest
from app.core.config import settings
from app.core.security import decode_qris_ktp

def test_qris_symmetric_xor_obfuscation():
    # 1. Setup a test NIK and shared secret key
    original_nik = "3171123456789012"
    secret_key = settings.QRIS_SECRET_KEY
    
    # 2. Simulate Frontend XOR encryption and Base64 encoding
    raw_bytes = original_nik.encode('utf-8')
    key_bytes = secret_key.encode('utf-8')
    
    xor_bytes = bytes([raw_bytes[i] ^ key_bytes[i % len(key_bytes)] for i in range(len(raw_bytes))])
    base64_encoded = base64.b64encode(xor_bytes).decode('utf-8')
    qr_string = f"MYSUF-QRIS:KTP:{base64_encoded}"
    
    # 3. Verify that the simulated string starts with the proper prefix and has the base64 payload
    assert qr_string.startswith("MYSUF-QRIS:KTP:")
    
    # 4. Use backend security decoding helper to decrypt
    decoded_nik = decode_qris_ktp(qr_string)
    
    # 5. Confirm that the decrypted NIK perfectly matches the original unmasked NIK
    assert decoded_nik == original_nik

def test_qris_decoding_with_invalid_prefix():
    # Attempting to decode an invalid QRIS format should raise ValueError
    invalid_qr = "INVALID-PREFIX:MzE3MTEyMzQ1Njc4OTAxMg=="
    with pytest.raises(ValueError) as excinfo:
        decode_qris_ktp(invalid_qr)
    
    assert "Invalid QRIS code format or prefix mismatch" in str(excinfo.value)
