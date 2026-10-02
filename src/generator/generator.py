import json
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Generator, List, Optional, Tuple

from faker import Faker

from src.common.config import settings
from src.common.logger import get_logger
from src.common.models import DeviceSignal, IdentityEvent, TransactionEvent, TransactionStatus

logger = get_logger("generator")
fake = Faker()


class SyntheticEventGenerator:
    """
    High-fidelity Synthetic Transaction and Identity Generator for Fraud Engineering.
    Produces normal activity, velocity attacks, synthetic identity rings, ATO, and mule networks.
    """

    def __init__(
        self,
        num_legit_users: int = 200,
        num_fraud_rings: int = 5,
        ring_size: int = 6,
        fraud_ratio: float = 0.15,
        seed: int = 42,
    ):
        random.seed(seed)
        Faker.seed(seed)
        self.fraud_ratio = fraud_ratio
        self.num_legit_users = num_legit_users
        self.num_fraud_rings = num_fraud_rings
        self.ring_size = ring_size

        # Pre-generate legitimate user profiles
        self.legit_users = self._generate_legit_users(self.num_legit_users)

        # Pre-generate coordinated fraud rings (sharing devices, IPs, or SSNs)
        self.fraud_rings = self._generate_fraud_rings(self.num_fraud_rings, self.ring_size)

        # Known blacklisted test data
        self.blacklisted_ips = ["198.51.100.42", "203.0.113.88"]
        self.blacklisted_devices = ["fp_emul_999a888b777c"]
        self.blacklisted_cards = ["tok_card_fraud_stolen_411111"]

        # Common merchant pool
        self.merchants = [
            f"merch_{fake.company().lower().replace(' ', '_').replace(',', '')[:16]}"
            for _ in range(30)
        ]

        logger.info(
            f"Initialized SyntheticEventGenerator with {len(self.legit_users)} legitimate users and "
            f"{len(self.fraud_rings)} fraud rings (total {len(self.fraud_rings) * ring_size} ring members)."
        )

    def _generate_legit_users(self, count: int) -> List[Dict]:
        users = []
        for _ in range(count):
            user_id = f"usr_{uuid.uuid4().hex[:12]}"
            device_id = f"dev_{uuid.uuid4().hex[:12]}"
            device_fp = f"fp_{uuid.uuid4().hex[:16]}"
            ip = fake.ipv4_public()
            card = f"tok_card_{uuid.uuid4().hex[:12]}"
            bank = f"act_{uuid.uuid4().hex[:10]}"
            email = fake.ascii_email()
            phone = fake.msisdn()[:12]
            name = fake.name()
            national_id = f"SSN-{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}"

            users.append(
                {
                    "user_id": user_id,
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "national_id": national_id,
                    "device_id": device_id,
                    "device_fingerprint": device_fp,
                    "ip_address": ip,
                    "card_token": card,
                    "bank_account": bank,
                    "os": random.choice(["iOS", "Android", "macOS", "Windows"]),
                    "browser": random.choice(["Safari", "Chrome", "Firefox", "Edge"]),
                    "is_emulator": False,
                    "is_rooted": False,
                    "country": "US",
                    "city": fake.city(),
                }
            )
        return users

    def _generate_fraud_rings(self, num_rings: int, ring_size: int) -> List[List[Dict]]:
        rings = []
        for r_idx in range(num_rings):
            shared_device_id = f"dev_shared_ring_{r_idx}_{uuid.uuid4().hex[:8]}"
            shared_device_fp = f"fp_shared_ring_{r_idx}_{uuid.uuid4().hex[:12]}"
            shared_ip = f"192.0.2.{10 + r_idx}"
            shared_national_id = (
                f"SSN-SYNTH-{900 + r_idx}-{random.randint(10, 99)}-{random.randint(1000, 9999)}"
            )
            shared_phone = f"+1555019{random.randint(100, 999)}"

            ring_members = []
            for m_idx in range(ring_size):
                member_user_id = f"usr_ring_{r_idx}_m{m_idx}_{uuid.uuid4().hex[:8]}"
                ring_members.append(
                    {
                        "user_id": member_user_id,
                        "name": fake.name(),
                        "email": f"ring{r_idx}_m{m_idx}_{fake.user_name()}@fraudring.net",
                        "phone": shared_phone if random.random() < 0.7 else fake.msisdn()[:12],
                        "national_id": shared_national_id,
                        "device_id": shared_device_id,
                        "device_fingerprint": shared_device_fp,
                        "ip_address": shared_ip,
                        "card_token": f"tok_card_ring_{r_idx}_{m_idx}_{uuid.uuid4().hex[:8]}",
                        "bank_account": f"act_ring_mule_{r_idx}_{uuid.uuid4().hex[:8]}",
                        "os": "Android",
                        "browser": "Chrome",
                        "is_emulator": True if random.random() < 0.6 else False,
                        "is_rooted": True if random.random() < 0.5 else False,
                        "country": "US",
                        "city": "Chicago",
                        "ring_id": f"ring_{r_idx}",
                    }
                )
            rings.append(ring_members)
        return rings

    def generate_single_event(self) -> Tuple[TransactionEvent, Optional[IdentityEvent]]:
        """
        Generates a realistic transaction event and corresponding identity registration/update event.
        Injects fraud vectors based on self.fraud_ratio.
        """
        is_fraud = random.random() < self.fraud_ratio
        fraud_type = (
            random.choice(["ring", "velocity", "ato", "blacklist", "amount"])
            if is_fraud
            else "none"
        )

        now_utc = datetime.now(timezone.utc)

        if fraud_type == "ring":
            # Select random member from a fraud ring (sharing device/IP/SSN)
            ring = random.choice(self.fraud_rings)
            user_profile = random.choice(ring)
            amount = round(random.uniform(250.0, 4800.0), 2)
            merchant = random.choice(self.merchants)

        elif fraud_type == "velocity":
            # Rapid micro-transactions or brute force
            user_profile = random.choice(self.legit_users)
            amount = round(random.uniform(5.0, 99.0), 2)
            merchant = random.choice(self.merchants)

        elif fraud_type == "ato":
            # Account Takeover: sudden foreign IP, strange emulator device, high amount
            victim = random.choice(self.legit_users)
            user_profile = dict(victim)
            user_profile["ip_address"] = fake.ipv4_public()
            user_profile["device_id"] = f"dev_ato_{uuid.uuid4().hex[:8]}"
            user_profile["device_fingerprint"] = f"fp_ato_{uuid.uuid4().hex[:12]}"
            user_profile["is_emulator"] = True
            user_profile["city"] = "Lagos"
            user_profile["country"] = "NG"
            amount = round(random.uniform(6000.0, 18500.0), 2)
            merchant = random.choice(self.merchants)

        elif fraud_type == "blacklist":
            # Hit known malicious blacklist
            victim = random.choice(self.legit_users)
            user_profile = dict(victim)
            user_profile["ip_address"] = random.choice(self.blacklisted_ips)
            user_profile["device_fingerprint"] = random.choice(self.blacklisted_devices)
            user_profile["card_token"] = random.choice(self.blacklisted_cards)
            amount = round(random.uniform(50.0, 2000.0), 2)
            merchant = random.choice(self.merchants)

        elif fraud_type == "amount":
            # Unusually large transaction amount
            user_profile = random.choice(self.legit_users)
            amount = round(random.uniform(16000.0, 35000.0), 2)
            merchant = random.choice(self.merchants)

        else:
            # Normal legitimate user transaction
            user_profile = random.choice(self.legit_users)
            amount = round(random.expovariate(1 / 45.0) + 2.0, 2)
            amount = min(amount, 1200.0)
            merchant = random.choice(self.merchants)

        device_sig = DeviceSignal(
            device_id=user_profile["device_id"],
            device_fingerprint=user_profile["device_fingerprint"],
            os=user_profile.get("os", "iOS"),
            browser=user_profile.get("browser", "Safari"),
            is_emulator=user_profile.get("is_emulator", False),
            is_rooted=user_profile.get("is_rooted", False),
        )

        tx_event = TransactionEvent(
            transaction_id=f"tx_{uuid.uuid4().hex[:14]}",
            user_id=user_profile["user_id"],
            amount=amount,
            currency="USD",
            transaction_type=random.choice(["PAYMENT", "TRANSFER", "CHECKOUT"]),
            payment_method=random.choice(["CARD", "ACH", "WALLET"]),
            card_token=user_profile.get("card_token"),
            bank_account=user_profile.get("bank_account"),
            merchant_id=merchant,
            device_id=user_profile["device_id"],
            ip_address=user_profile["ip_address"],
            location_country=user_profile.get("country", "US"),
            location_city=user_profile.get("city", "New York"),
            device_signals=device_sig,
            timestamp=now_utc,
            status=TransactionStatus.COMPLETED,
            metadata={
                "fraud_type_injected": fraud_type,
                "is_synthetic_fraud": is_fraud,
                "ring_id": user_profile.get("ring_id"),
            },
        )

        # Generate corresponding Identity profile event
        identity_event = IdentityEvent(
            user_id=user_profile["user_id"],
            email=user_profile["email"],
            phone=user_profile.get("phone"),
            full_name=user_profile.get("name"),
            national_id=user_profile.get("national_id"),
            kyc_status=(
                "VERIFIED" if not is_fraud else random.choice(["PENDING", "VERIFIED", "FLAGGED"])
            ),
            risk_tier="HIGH" if is_fraud else "STANDARD",
            device=device_sig,
            ip_address=user_profile["ip_address"],
            timestamp=now_utc,
        )

        return tx_event, identity_event

    def generate_stream(
        self, rate_per_sec: float = 5.0, max_events: Optional[int] = None
    ) -> Generator[Tuple[TransactionEvent, IdentityEvent], None, None]:
        """
        Yields continuous transaction stream at configured rate.
        """
        interval = 1.0 / max(rate_per_sec, 0.1)
        emitted = 0

        while max_events is None or emitted < max_events:
            tx, ident = self.generate_single_event()
            yield tx, ident
            emitted += 1
            if rate_per_sec > 0:
                time.sleep(interval)


def publish_to_kafka(
    bootstrap_servers: str,
    rate_per_sec: float = 10.0,
    count: Optional[int] = None,
    fraud_ratio: float = 0.15,
):
    """
    Streams generated synthetic transactions and identities into Kafka topics.
    """
    try:
        from kafka import KafkaProducer
    except ImportError:
        logger.error("kafka-python is not installed. Please install requirements.")
        return

    logger.info(f"Connecting KafkaProducer to {bootstrap_servers}...")
    producer = KafkaProducer(
        bootstrap_servers=bootstrap_servers.split(","),
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        acks=1,
        retries=3,
    )

    gen = SyntheticEventGenerator(fraud_ratio=fraud_ratio)
    emitted = 0

    logger.info(
        f"Starting Kafka stream to {settings.KAFKA_RAW_TRANSACTIONS_TOPIC} at {rate_per_sec} events/sec..."
    )

    try:
        for tx, ident in gen.generate_stream(rate_per_sec=rate_per_sec, max_events=count):
            # Publish transaction
            producer.send(
                topic=settings.KAFKA_RAW_TRANSACTIONS_TOPIC, key=tx.user_id, value=tx.model_dump()
            )

            # Publish identity registration/signals
            if ident:
                producer.send(
                    topic=settings.KAFKA_RAW_IDENTITY_TOPIC,
                    key=ident.user_id,
                    value=ident.model_dump(),
                )

            emitted += 1
            if emitted % 100 == 0:
                producer.flush()
                logger.info(f"Emitted {emitted} transactions to Kafka.")

    except KeyboardInterrupt:
        logger.info("Kafka streaming stopped by user.")
    finally:
        producer.flush()
        producer.close()
        logger.info(f"Finished. Total transactions emitted: {emitted}")
