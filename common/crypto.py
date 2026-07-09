# -*- coding: utf-8 -*-
"""共享加密层：TLS 自签名证书生成与 SSL 上下文创建。"""

import ssl
import os
import ipaddress
import logging
import socket

logger = logging.getLogger(__name__)

# cryptography 不可用时的降级标志
_CRYPTO_AVAILABLE = False

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import datetime

    _CRYPTO_AVAILABLE = True
except ImportError:
    logger.warning("cryptography 库不可用，TLS 功能将降级为 None")


def generate_self_signed_cert(cert_dir: str):
    """生成自签名 TLS 证书（cert.pem 和 key.pem），保存到 cert_dir 目录。

    使用 RSA 2048 位密钥，有效期 365 天，CN="WinConsole"。

    Args:
        cert_dir: 证书保存目录

    Returns:
        成功时返回 (cert_path, key_path) 元组；
        如果 cryptography 不可用则返回 None。
    """
    if not _CRYPTO_AVAILABLE:
        logger.error("cryptography 库不可用，无法生成自签名证书")
        return None

    try:
        os.makedirs(cert_dir, exist_ok=True)

        # 生成 RSA 2048 位私钥
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # 构建证书主题和颁发者（自签名，两者相同）
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "WinConsole"),
        ])

        san_entries = [
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        ]
        try:
            hostname = socket.gethostname()
            if hostname:
                san_entries.append(x509.DNSName(hostname))
        except Exception:
            pass
        try:
            fqdn = socket.getfqdn()
            if fqdn and fqdn != socket.gethostname():
                san_entries.append(x509.DNSName(fqdn))
        except Exception:
            pass
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            if local_ip and local_ip != "127.0.0.1":
                san_entries.append(x509.IPAddress(ipaddress.IPv4Address(local_ip)))
        except Exception:
            pass

        # 构建证书
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
            .sign(key, hashes.SHA256())
        )

        cert_path = os.path.join(cert_dir, "cert.pem")
        key_path = os.path.join(cert_dir, "key.pem")

        # 写入证书文件
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        # 写入私钥文件
        with open(key_path, "wb") as f:
            f.write(
                key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        logger.info("自签名证书已生成: %s, %s", cert_path, key_path)
        return cert_path, key_path

    except Exception as e:
        logger.error("生成自签名证书失败: %s", e)
        return None


def create_ssl_context(cert_dir: str, auto_generate: bool = False):
    """从 cert_dir 加载证书创建 ssl.SSLContext。

    Args:
        cert_dir: 包含 cert.pem 和 key.pem 的目录
        auto_generate: 证书不存在时是否自动生成自签名证书

    Returns:
        ssl.SSLContext 实例；
        如果 cryptography 不可用或加载失败则返回 None。
    """
    if not _CRYPTO_AVAILABLE:
        logger.error("cryptography 库不可用，无法创建 SSL 上下文")
        return None

    try:
        cert_path = os.path.join(cert_dir, "cert.pem")
        key_path = os.path.join(cert_dir, "key.pem")

        if auto_generate and (not os.path.exists(cert_path) or not os.path.exists(key_path)):
            generate_self_signed_cert(cert_dir)

        if not os.path.exists(cert_path) or not os.path.exists(key_path):
            logger.error("证书文件不存在: %s / %s", cert_path, key_path)
            return None

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
        logger.info("SSL 上下文已创建，证书目录: %s", cert_dir)
        return ctx

    except Exception as e:
        logger.error("创建 SSL 上下文失败: %s", e)
        return None
