import os
import grpc
import logging
from concurrent import futures

import generated.spotify_pb2 as spotify_pb2
import generated.spotify_pb2_grpc as spotify_pb2_grpc


class SpotifyService(spotify_pb2_grpc.SpotifyServiceServicer):
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Core service initialized")

    def PlaySong(self, request, context):

        try:
            self.logger.info(f"Song to be played: {request.name}")

            response = spotify_pb2.SpotifyResponse(
                response="Fuck yeah!",
                success=True,
            )

            response_message = "Fuck yeah!"

            self.logger.info(f"Responding with response '{response_message}'")

            return response

        except Exception as e:
            self.logger.error(f"Error processing message: {str(e)}")

            # Return error response
            return spotify_pb2.SpotifyResponse(
                response=f'Sorry, I encountered an error trying to play the song ${request.name}',
                success=False,
                error_message=str(e)
            )

    def HealthCheck(self, request, context):
        try:
            return spotify_pb2.HealthResponse(
                status="healthy",
                message="Spotify service is running normally"
            )
        except Exception as e:
            return spotify_pb2.HealthResponse(
                status="unhealthy",
                message=f"Error: {str(e)}"
            )

def serve():

    port = os.getenv('GRPC_PORT', '50051')

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))

    spotify_service = SpotifyService()
    spotify_pb2_grpc.add_SpotifyServiceServicer_to_server(spotify_service, server)

    listen_addr = f'[::]:{port}'
    server.add_insecure_port(listen_addr)
    server.start()

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == '__main__':
    serve()