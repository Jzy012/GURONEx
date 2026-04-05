from channels.generic.websocket import AsyncJsonWebsocketConsumer


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return

        if user.role not in {"admin", "system_admin", "faculty"}:
            await self.close(code=4403)
            return

        self.group_name = f"notifications_user_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def notification_message(self, event):
        await self.send_json(
            {
                "event": event.get("event"),
                "payload": event.get("payload", {}),
            }
        )
