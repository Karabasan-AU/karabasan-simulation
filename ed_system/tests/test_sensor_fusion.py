import unittest
from unittest.mock import MagicMock, patch
import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from sensor_fusion import SensorFusion

class TestSensorFusion(unittest.TestCase):
    @patch('zmq.Context') # ZeroMQ'yu tamamen sahtele (Port çakışmasını önle)
    def setUp(self, mock_zmq_context):
        # Config dosyasını okumadan geçmesi için mock open kullanıyoruz
        with patch('builtins.open', unittest.mock.mock_open(read_data='{}')):
            self.sf = SensorFusion(config_file='dummy.json')
            
        # Gönderme soketlerini (ui_pub ve trigger_pub) izlemek için sahtele
        self.sf.ui_pub = MagicMock()
        self.sf.trigger_pub = MagicMock()

    def test_handle_telemetry_ui_logging(self):
        """Gelen sıradan bir telemetrinin UI arayüzüne timestamp ile loglandığını test eder."""
        dummy_payload = b"NORMAL_WEATHER_DATA: 25C"
        
        self.sf._handle_telemetry(dummy_payload)
        
        # Arayüze mesaj basılmış mı kontrol et
        self.sf.ui_pub.send_multipart.assert_called_once()
        
        # Basılan mesajın içeriğini (argümanları) al
        args, _ = self.sf.ui_pub.send_multipart.call_args
        topic, msg_bytes = args[0]
        
        self.assertEqual(topic, b"ui.data")
        
        # JSON içeriğinde timestamp var mı?
        msg_dict = json.loads(msg_bytes.decode('utf-8'))
        self.assertIn("timestamp", msg_dict)
        self.assertEqual(msg_dict["type"], "telemetry")

    def test_handle_telemetry_attack_trigger(self):
        """İçinde 'DRONE_ID' geçen kritik verinin ET modülünü tetiklediğini test eder."""
        critical_payload = b"TARGET SPOTTED - DRONE_ID: 1453"
        
        self.sf._handle_telemetry(critical_payload)
        
        # Taarruz emri basılmış mı kontrol et
        self.sf.trigger_pub.send_multipart.assert_called_once()
        
        # Emrin detaylarını (argümanları) al
        args, _ = self.sf.trigger_pub.send_multipart.call_args
        topic, msg_bytes = args[0]
        
        self.assertEqual(topic, b"et.trigger")
        
        # JSON komutu doğru formatta mı?
        cmd_dict = json.loads(msg_bytes.decode('utf-8'))
        self.assertEqual(cmd_dict["action"], "START_JAMMING")
        self.assertEqual(cmd_dict["priority"], "HIGH")

    def test_handle_telemetry_no_attack(self):
        """Kritik kelime içermeyen verilerde ET modülünün sessiz kaldığını test eder."""
        safe_payload = b"GPS_OK_NO_THREAT"
        
        self.sf._handle_telemetry(safe_payload)
        
        # Taarruz emri KESİNLİKLE basılmamış olmalı!
        self.sf.trigger_pub.send_multipart.assert_not_called()

if __name__ == '__main__':
    unittest.main()