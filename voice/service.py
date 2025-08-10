import grpc
import time
from concurrent import futures

import os
from concurrent import futures
from dotenv import load_dotenv
from elevenlabs import play
from elevenlabs.client import ElevenLabs
from pvrecorder import PvRecorder
import pvporcupine
import pvcheetah
import threading

import openwakeword

from openwakeword.model import Model
import numpy as np

import generated.voice_pb2 as voice_pb2
import generated.voice_pb2_grpc as voice_pb2_grpc


load_dotenv()


class VoiceService(voice_pb2_grpc.VoiceServiceServicer):
    def __init__(self):

        self.sample_rate = 16000
        self.frame_duration_ms = 80
        self.frame_samples = int(self.sample_rate * self.frame_duration_ms / 1000)  # 1280 samples
        self.wake_word_running = False
        self.wake_word_thread = None

        self.THRESHOLD = float(os.getenv('WAKE_THRESHOLD'))
        if not self.THRESHOLD:
            self.THRESHOLD = 0.7

        self.timeout_duration = int(os.getenv('TIMEOUT_DURATION'))
        if not self.timeout_duration:
            self.timeout_duration = 10

        eleven_labs_key = os.getenv('ELEVENLABS_API_KEY')
        cheetah_key = os.getenv('PVCHEETAH_API_KEY')

        if not eleven_labs_key or not cheetah_key:
            raise ValueError("Necessary API keys not found in environment variables")

        self.elevenlabs_client = ElevenLabs(api_key=eleven_labs_key)
        self.recorder = PvRecorder(device_index=-1, frame_length=512)
        self.cheetah = pvcheetah.create(access_key=cheetah_key, endpoint_duration_sec=1.5)
        self.wake_model = Model(wakeword_model_paths=["Resources/hey_jarvis_v0.1.onnx"])

        # Start wake word detection
        self._start_wake_word_detection()

    def Speak(self, request, context):

        print(f"TTS Request: '{request.text}'")

        success = self._do_tts(request.text)

        return voice_pb2.SpeakResponse(
            success=success,
            message="Speech completed" if success else "TTS failed"
        )

    def _do_tts(self, text):

        print(f"Speaking: {text}")

        voice = os.getenv('ELEVEN_VOICE_ID')
        if not voice:
            raise ValueError("ELEVEN_VOICE_ID not found in environment variables")

        model = os.getenv('ELEVEN_MODEL')
        if not model:
            raise ValueError("ELEVEN_MODEL not found in environment variables")

        audio = self.elevenlabs_client.generate(
            text=text,
            voice=voice,
            model=model
        )

        if not audio:
            raise ValueError("Failed to generate audio")

        play(audio)

        return True

    def get_next_audio_frame(self):
        return self.recorder.read()

    def _start_wake_word_detection(self):
        """ Start the background wake word detection thread """

        if not self.wake_word_running:
            self.wake_word_running = True
            self.wake_word_thread = threading.Thread(
                target=self._wake_word_loop,
                daemon=True
            )
            self.wake_word_thread.start()
            print("Wake word detection started")

    def _wake_word_loop(self):
        """Background loop for wake word detection """
        try:
            self.recorder.start()
            print("Jarvis is now listening...")
            self._do_tts("Booting up!")

            while not self._stop_wake_word.is_set():
                try:
                    # Get audio frame and check for wake word
                    pcm = self.recorder.read()

                    if isinstance(pcm, bytes):
                        pcm = np.frombuffer(pcm, dtype=np.int16)

                    prediction = self.wake_model.predict(pcm)

                    for wakeword, score in prediction.items():
                        if score >= self.THRESHOLD:
                            print("Hello sir, how can I help you?")
                            self._process_speech_recognition()
                            break

                except Exception as e:
                    print(f"Error in wake word detection: {e}")
                    time.sleep(0.1)

        except Exception as e:
            print(f"Error starting wake word detection: {e}")
        finally:
            if self.recorder.is_recording:
                self.recorder.stop()

    def _process_speech_recognition(self):
        """Process speech after wake word detected"""
        self._do_tts("Yes sir?")

        result = ""
        start_time = time.time()

        try:
            while True:
                pcm = self.get_next_audio_frame()
                partial_transcript, is_endpoint = self.cheetah.process(pcm)
                result += partial_transcript

                if is_endpoint:
                    final_transcript = self.cheetah.flush()
                    result += final_transcript
                    break

                if time.time() - start_time >= self.timeout_duration:
                    print("Timeout reached. Exiting...")
                    break

            print(f"Recognized: {result}")

            response = self._process_command(result)
            self._do_tts(response)

        except Exception as e:
            print(f"Error processing speech: {e}")
            self._do_tts("Error processing command")

    def _process_command(self, command_text):
        """Explain"""
        # TODO
        return f"I heard you say: {command_text}"

    def WakeWordStream(self, request, context):
        """ Simple wake word stream """
        print("Client connected to wake word stream")

        try:
            # Just keep the connection alive and send periodic status
            while context.is_active():
                # Send a heartbeat every second
                event = voice_pb2.WakeWordEvent(
                    detected=False,
                    wake_word="jarvis"
                )
                yield event
                time.sleep(1.0)

        except Exception as e:
            print(f"Stream error: {e}")
        finally:
            print("Client disconnected from wake word stream")

    def shutdown(self):
        """Cleanup when shutting down"""
        print("Shutting down voice service...")
        self.wake_word_running = False
        #self._stop_wake_word.set()

        if self.wake_word_thread:
            self.wake_word_thread.join(timeout=2.0)

        # Clean up Picovoice resources
        if hasattr(self, 'recorder') and self.recorder.is_recording:
            self.recorder.stop()
        if hasattr(self, 'recorder'):
            self.recorder.delete()
        if hasattr(self, 'porcupine'):
            self.porcupine.delete()
        if hasattr(self, 'cheetah'):
            self.cheetah.delete()

def serve():
    """Start the gRPC server"""
    port = 50051
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))

    # Create service instance
    voice_service = VoiceService()

    # Add voice service to server
    voice_pb2_grpc.add_VoiceServiceServicer_to_server(voice_service, server)

    # Start server
    server.add_insecure_port(f'[::]:{port}')
    server.start()

    print(f"Voice service running on port {port}")

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("Shutting down...")
        voice_service.shutdown()
        server.stop(grace=5)


if __name__ == '__main__':
    serve()