import asyncio
import os
import grpc
import time
import logging
from concurrent import futures
from pathlib import Path

# Import generated protobuf files
import generated.core_pb2 as core_pb2
import generated.core_pb2_grpc as core_pb2_grpc
from registry import registry


class CoreService(core_pb2_grpc.CoreServiceServicer):
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Core service initialized")

    def ProcessMessage(self, request, context):

        try:

            raw_response = self.find_run_intent(request.message)

            if hasattr(raw_response, 'response'):
                response_message = raw_response.response
                self.logger.info(f"Extracted response field: '{response_message}'")
            elif isinstance(raw_response, str):

                if raw_response.startswith('response: '):

                    import re
                    match = re.search(r'response: "(.*?)"', raw_response)
                    if match:
                        response_message = match.group(1)
                    else:
                        response_message = raw_response
                else:
                    response_message = raw_response
            else:
                response_message = str(raw_response)

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

    def find_run_intent(self, command_string: str) -> str:

        words = command_string.lower().split()

        result = registry.find_command(words)

        print(f"Found command: {words}")

        if result:
            command, args = result

            output = command.handler(args)

            print("Intent:", " ".join(map(str, command.keywords)))
            print("Params:", args)
            print("Output:", output)

            return output
        else:
            print("No matching command found")
            return "No matching command found"

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