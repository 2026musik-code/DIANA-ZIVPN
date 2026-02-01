import requests
import hashlib
import logging

logger = logging.getLogger(__name__)

class PaymenkuClient:
    def __init__(self, merchant_id, api_key, base_url="https://paymenku.com/api"):
        self.merchant_id = merchant_id
        self.api_key = api_key
        self.base_url = base_url

    def generate_signature(self, ref_id, amount):
        """
        Generates signature for request.
        Common pattern: md5(merchant_id + ref_id + amount + api_key)
        Adjust this based on actual API docs.
        """
        raw_str = f"{self.merchant_id}{ref_id}{amount}{self.api_key}"
        return hashlib.md5(raw_str.encode()).hexdigest()

    def create_transaction(self, ref_id, amount, return_url=None, callback_url=None):
        """
        Creates a transaction and returns QR string/URL.
        """
        endpoint = f"{self.base_url}/create"
        signature = self.generate_signature(ref_id, amount)

        payload = {
            "merchant_id": self.merchant_id,
            "ref_id": ref_id,
            "amount": amount,
            "signature": signature,
            "return_url": return_url,
            "callback_url": callback_url
        }

        logger.info(f"Creating Paymenku transaction: {payload}")

        # MOCK REQUEST for development if no real API key
        if self.merchant_id == "mock":
             return {
                "success": True,
                "data": {
                    "qr_content": "00020101021226580016ID.CO.GOPAY.WWW01189360091800000000000215ID10200219668380303UMI51440014ID.CO.QRIS.WWW0215ID10200219668380303UMI5204581253033605802ID5911TEST MERCHANT6006JAKARTA61051234562070703A01630459B2",
                    "checkout_url": f"https://paymenku.com/process/{ref_id}"
                }
            }

        try:
            response = requests.post(endpoint, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Paymenku API Error: {e}")
            return {"success": False, "message": str(e)}

    def verify_callback_signature(self, data):
        """
        Verifies the signature from webhook callback.
        """
        # Assume callback sends: merchant_id, ref_id, amount, status, signature
        # verify = md5(merchant_id + ref_id + amount + status + api_key)

        received_signature = data.get('signature')
        ref_id = data.get('ref_id')
        amount = data.get('amount')
        status = data.get('status')

        raw_str = f"{self.merchant_id}{ref_id}{amount}{status}{self.api_key}"
        calculated_signature = hashlib.md5(raw_str.encode()).hexdigest()

        return received_signature == calculated_signature
