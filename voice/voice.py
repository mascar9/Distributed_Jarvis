import os
import time
import numpy as np

from dotenv import load_dotenv
from elevenlabs import play
from elevenlabs.client import ElevenLabs
from pvrecorder import PvRecorder
import pvcheetah
from openwakeword.model import Model
import grpc
import time
import sys

load_dotenv()

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

from core.generated import core_pb2
from core.generated import core_pb2_grpc


class VoiceService:
    def __init__(self, core_host='localhost', core_port=50051):

        self.core_address = f"{core_host}:{core_port}"
        self.channel = None
        self.stub = None
        self.connect_to_core()


        self.THRESHOLD = float(os.getenv('WAKE_THRESHOLD', 0.7))
        self.timeout_duration = int(os.getenv('TIMEOUT_DURATION', 10))

        eleven_labs_key = os.getenv('ELEVENLABS_API_KEY')
        cheetah_key = os.getenv('PVCHEETAH_API_KEY')

        if not eleven_labs_key or not cheetah_key:
            raise ValueError("Necessary API keys not found in environment variables")

        self.elevenlabs_client = ElevenLabs(api_key=eleven_labs_key)
        self.recorder = PvRecorder(device_index=-1, frame_length=512)
        self.cheetah = pvcheetah.create(access_key=cheetah_key, endpoint_duration_sec=1.5)
        self.wake_model = Model(wakeword_model_paths=["Resources/hey_jarvis_v0.1.onnx"])

    def connect_to_core(self):
        """Establish gRPC connection to Core service"""
        try:
            print(f"Connecting to Core service at {self.core_address}...")
            self.channel = grpc.insecure_channel(self.core_address)
            self.stub = core_pb2_grpc.CoreServiceStub(self.channel)

            health_request = core_pb2.HealthRequest(service="voice")
            health_response = self.stub.HealthCheck(health_request)

            if health_response.status == "healthy":
                print(f"✅ Connected to Core service successfully!")
                print(f"   Status: {health_response.message}")
            else:
                print(f"⚠️ Core service is unhealthy: {health_response.message}")

        except grpc.RpcError as e:
            print(f"❌ Failed to connect to Core service: {e}")
            self.channel = None
            self.stub = None

    def send_message(self, message):
        """Send a message to Core service and get response"""
        if not self.stub:
            print("❌ Not connected to Core service")
            return None

        try:

            request = core_pb2.MessageRequest(
                message=message,
                source="voice",
                timestamp=int(time.time())
            )

            print(f"Sending: '{message}'")

            response = self.stub.ProcessMessage(request)

            if response.success:
                print(f"Core responded: '{response.response}'")
                return response.response
            else:
                print(f"Error from Core: {response.error_message}")
                return "Failed to retrieve response"

        except grpc.RpcError as e:
            print(f"gRPC error: {e}")
            return None

    def _do_tts(self, text):
        print(f"Speaking: {text}")

        voice = os.getenv('ELEVEN_VOICE_ID')
        model = os.getenv('ELEVEN_MODEL')

        if not voice or not model:
            raise ValueError("ELEVEN_VOICE_ID or ELEVEN_MODEL not found in environment variables")

        audio = self.elevenlabs_client.generate(
            text=text,
            voice=voice,
            model=model
        )

        if not audio:
            raise ValueError("Failed to generate audio")

        play(audio)
        return True

    def listen_for_wake_word(self):
        print("Starting wake word detection...")
        self.recorder.start()
        self._do_tts("Booting up!")

        try:
            while True:
                pcm = self.recorder.read()
                if isinstance(pcm, bytes):
                    pcm = np.frombuffer(pcm, dtype=np.int16)

                prediction = self.wake_model.predict(pcm)

                for wakeword, score in prediction.items():
                    if score >= self.THRESHOLD:
                        print(f"Score: {score}")
                        print("Wake word detected!")

                        self._process_speech_recognition()

                        print("Returning to wake word detection...")

                        self.wake_model = Model(wakeword_model_paths=["Resources/hey_jarvis_v0.1.onnx"])

                        break

        except KeyboardInterrupt:
            print("Stopping wake word detection.")
        finally:
            if self.recorder.is_recording:
                self.recorder.stop()

    def _process_speech_recognition(self):
        self._do_tts("Yes sir?")
        result = ""
        start_time = time.time()

        if not self.recorder.is_recording:
            self.recorder.start()

        try:
            while True:
                pcm = self.recorder.read()
                partial_transcript, is_endpoint = self.cheetah.process(pcm)
                result += partial_transcript

                if is_endpoint:
                    final_transcript = self.cheetah.flush()
                    result += final_transcript
                    break

                if time.time() - start_time >= self.timeout_duration:
                    print("Timeout reached. Exiting speech recognition.")
                    break

            print(f"Recognized command: {result}")

            response = self._process_command(result)
            self._do_tts(response)

        except Exception as e:
            print(f"Error during speech recognition: {e}")
            self._do_tts("Error processing command")
        #finally:
            #if self.recorder.is_recording:
                #self.recorder.stop()

    def _process_command(self, command_text):

        return self.send_message(message=command_text)

    def shutdown(self):
        if hasattr(self, 'recorder') and self.recorder.is_recording:
            self.recorder.stop()
            self.recorder.delete()
        if hasattr(self, 'cheetah'):
            self.cheetah.delete()
        print("Voice service shut down.")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python voice.py <message>")
        sys.exit(1)

    message = " ".join(sys.argv[1:])

    voice_service = VoiceService()
    try:
        voice_service.send_message(message)
    finally:
        voice_service.shutdown()