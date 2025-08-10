import os
import grpc
import time
import logging
from concurrent import futures
from pathlib import Path

# Import generated protobuf files
import generated.core_pb2 as core_pb2
import generated.core_pb2_grpc as core_pb2_grpc


class CoreService(core_pb2_grpc.CoreServiceServicer):
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Core service initialized")

    def ProcessMessage(self, request, context):
        """
        Main message processing endpoint
        Receives messages from voice.py, telegram, etc.
        """
        try:
            # Log the incoming request
            self.logger.info(f"Received message from {request.source}: '{request.message}'")

            # Extract intent and generate response
            intent, response_message = self.extract_intent(request.message)

            # Create response
            response = core_pb2.MessageResponse(
                response=response_message,
                success=True,
                error_message=""
            )

            self.logger.info(f"Responding with response '{response_message}'")
            return response

        except Exception as e:
            self.logger.error(f"Error processing message: {str(e)}")

            # Return error response
            return core_pb2.MessageResponse(
                response="Sorry, I encountered an error processing your message.",
                success=False,
                error_message=str(e)
            )

    def extract_intent(self, message):
        """
        Simple intent extraction logic
        This is where the magic happens - analyzing the message and determining intent
        """
        # Convert to lowercase for easier matching
        message_lower = message.lower().strip()

        # Split message into words
        words = message_lower.split()

        # Simple intent detection
        if any(word in words for word in ["hello", "hi", "hey", "greetings"]):
            return "greeting", "Hello! How can I help you?"

        elif any(word in words for word in ["bye", "goodbye", "see", "later"]):
            return "farewell", "Goodbye! Have a great day!"

        elif any(word in words for word in ["how", "are", "you"]):
            return "status_inquiry", "I'm doing great, thank you for asking!"

        elif any(word in words for word in ["time", "what", "clock"]):
            current_time = time.strftime("%H:%M:%S")
            return "time_request", f"The current time is {current_time}"

        elif any(word in words for word in ["help", "assist", "support"]):
            return "help_request", "I'm here to help! You can ask me about time, say hello, or just chat."

        elif any(word in words for word in ["weather", "temperature", "forecast"]):
            return "weather_request", "I don't have weather data yet, but I'd love to help with that in the future!"

        else:
            return "unknown", "I don't know what that is"

    def HealthCheck(self, request, context):
        try:
            return core_pb2.HealthResponse(
                status="healthy",
                message="Core service is running normally"
            )
        except Exception as e:
            return core_pb2.HealthResponse(
                status="unhealthy",
                message=f"Error: {str(e)}"
            )


def serve():

    port = os.getenv('GRPC_PORT', '50051')

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))

    core_service = CoreService()
    core_pb2_grpc.add_CoreServiceServicer_to_server(core_service, server)

    listen_addr = f'[::]:{port}'
    server.add_insecure_port(listen_addr)
    server.start()

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == '__main__':
    serve()