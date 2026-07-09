# -*- coding: utf-8 -*-
"""客户端核心引擎：负责 WebSocket 连接管理、注册、心跳、消息收发与分发。"""

import asyncio
import json
import socket
import platform
import logging
import time
import base64
import ssl
from pathlib import Path

import websockets

# 导入共享模块
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.protocol import MsgType, encode_msg, decode_msg, make_msg
from common.config import *


class ClientEngine:
    """客户端核心引擎，管理与服务端的 WebSocket 连接及消息通信。"""

    def __init__(self, server_addr, auth_key='', use_tls=False,
                 tls_verify=True, ca_cert=''):
        """
        初始化客户端引擎。

        Args:
            server_addr: 服务端地址，格式 "ip:port"
            auth_key: 认证密钥（可选）
            use_tls: 是否使用 wss:// 连接
            tls_verify: 是否校验证书
            ca_cert: 自定义 CA 证书路径
        """
        self.server_addr = server_addr
        self.auth_key = auth_key
        self.use_tls = use_tls
        self.tls_verify = tls_verify
        self.ca_cert = ca_cert
        self.ws = None
        self.client_id = None
        self.running = False
        self.handlers = {}       # 消息类型(str) → 处理函数
        self._heartbeat_task = None
        self._loop = None
        self.logger = logging.getLogger('client.engine')

    # ------------------------------------------------------------------
    # 连接与注册
    # ------------------------------------------------------------------

    async def connect(self):
        """连接服务端，注册并启动心跳和消息接收循环。"""
        uri = self._build_uri()
        self.logger.info("正在连接服务端: %s", uri)
        self.ws = await websockets.connect(uri, ssl=self._build_ssl_context(uri))
        self.logger.info("已连接服务端")

        # 注册
        await self._register()

        # 启动心跳任务
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # 进入消息接收循环（阻塞，直到连接断开）
        try:
            await self._recv_loop()
        finally:
            # 清理心跳任务
            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass
            # 关闭连接
            if self.ws:
                await self.ws.close()
                self.ws = None
            self.logger.info("连接已关闭")

    async def _register(self):
        """收集本机信息并发送注册消息，等待 REGISTER_ACK 获取 client_id。"""
        hostname = socket.gethostname()
        os_name = platform.system()
        local_ip = self._get_local_ip()
        os_version = platform.version()
        arch = platform.machine()

        payload = {
            'hostname': hostname,
            'os': os_name,
            'ip': local_ip,
            'os_version': os_version,
            'arch': arch,
            'auth_key': self.auth_key,
        }

        msg = make_msg(MsgType.REGISTER, payload=payload)
        await self.send_msg(msg)
        self.logger.info("已发送注册消息")

        # 等待 REGISTER_ACK
        data = await self.ws.recv()
        ack_msg = decode_msg(data)
        if ack_msg.get('type') == MsgType.REGISTER_ACK.value:
            self.client_id = ack_msg.get('client_id', '')
            self.logger.info("注册成功，client_id=%s", self.client_id)
        else:
            payload = ack_msg.get('payload', {})
            error = payload.get('error', '未知错误') if isinstance(payload, dict) else '未知错误'
            raise RuntimeError(f"注册失败: {error}")

    def _build_uri(self):
        """根据地址和 TLS 配置生成 WebSocket URI。"""
        if self.server_addr.startswith(('ws://', 'wss://')):
            return self.server_addr
        scheme = 'wss' if self.use_tls else 'ws'
        return f"{scheme}://{self.server_addr}"

    def _build_ssl_context(self, uri):
        """为 wss:// 连接创建 SSL 上下文。"""
        if not uri.startswith('wss://'):
            return None

        if not self.tls_verify:
            return ssl._create_unverified_context()

        if self.ca_cert:
            return ssl.create_default_context(cafile=self.ca_cert)

        return ssl.create_default_context()

    @staticmethod
    def _get_local_ip():
        """获取本机局域网 IP 地址。"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return '127.0.0.1'

    # ------------------------------------------------------------------
    # 心跳
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self):
        """定期发送心跳消息，保持连接活跃。"""
        while self.running and self.ws:
            try:
                msg = make_msg(MsgType.HEARTBEAT, client_id=self.client_id or '')
                await self.send_msg(msg)
                await asyncio.sleep(HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("心跳发送失败: %s", e)
                break

    # ------------------------------------------------------------------
    # 消息收发
    # ------------------------------------------------------------------

    async def _recv_loop(self):
        """持续接收消息，根据类型分发到对应处理器。"""
        while self.running and self.ws:
            try:
                data = await self.ws.recv()
                msg = decode_msg(data)
                msg_type = msg.get('type', '')

                if msg_type == MsgType.HEARTBEAT_REQ.value:
                    # 心跳请求：立即回复心跳
                    reply = make_msg(MsgType.HEARTBEAT, client_id=self.client_id or '')
                    await self.send_msg(reply)

                elif msg_type == MsgType.CONFIG.value:
                    self._handle_config(msg)

                elif msg_type == MsgType.DISCONNECT.value:
                    self.logger.info("收到断开连接指令")
                    self.running = False
                    break

                elif msg_type in self.handlers:
                    handler = self.handlers[msg_type]
                    await handler(self, msg)

                else:
                    self.logger.warning("未处理的消息类型: %s", msg_type)

            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("连接已断开")
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("消息接收错误: %s", e)
                break

    def _handle_config(self, msg):
        """处理服务端下发的配置更新。"""
        payload = msg.get('payload', {})
        self.logger.info("收到配置更新: %s", payload)
        # TODO: 根据 payload 更新本地运行时配置

    async def send_msg(self, msg):
        """
        发送消息到服务端。

        Args:
            msg: 消息字典，包含 type、client_id、payload、seq 字段
        """
        data = encode_msg(msg)
        await self.ws.send(data)

    # ------------------------------------------------------------------
    # 重连
    # ------------------------------------------------------------------

    async def _reconnect_loop(self):
        """连接断开时定期重连，重连成功后重新注册。"""
        while self.running:
            try:
                await self.connect()
            except Exception as e:
                self.logger.error("连接异常: %s", e)

            if self.running:
                self.logger.info("%d 秒后尝试重连...", RECONNECT_INTERVAL)
                await asyncio.sleep(RECONNECT_INTERVAL)

    # ------------------------------------------------------------------
    # Handler 注册
    # ------------------------------------------------------------------

    def register_handler(self, msg_type, handler):
        """
        注册消息处理器。

        Args:
            msg_type: 消息类型，MsgType 枚举或字符串
            handler: 异步处理函数，签名 async def handler(msg)
        """
        key = msg_type.value if isinstance(msg_type, MsgType) else msg_type
        self.handlers[key] = handler
        self.logger.info("已注册消息处理器: %s", key)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def run(self):
        """主入口，启动连接和重连循环。"""
        self.running = True
        self._loop = asyncio.get_event_loop()
        self.logger.info("客户端引擎启动，目标服务端: %s", self.server_addr)
        await self._reconnect_loop()

    async def stop(self):
        """停止运行，关闭连接。"""
        self.running = False
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        if self.ws:
            await self.ws.close()
            self.ws = None
        self.logger.info("客户端引擎已停止")
