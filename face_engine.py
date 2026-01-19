def safe_import_cv2():
    try:
        import cv2
        return cv2
    except Exception as e:
        raise RuntimeError("OpenCV not available (Railway headless)") from e


def safe_import_np():
    import numpy as np
    return np

import numpy as np
import pickle
import os
import time
from typing import Tuple, Optional, Dict
from config import Config

# Global MediaPipe instances (thread-safe singleton)
_mp_face_mesh = None
_face_mesh_instance = None

def _init_mediapipe():
    """Initialize MediaPipe once globally"""
    global _mp_face_mesh, _face_mesh_instance
    
    if _face_mesh_instance is None:
        import mediapipe as mp
        _mp_face_mesh = mp.solutions.face_mesh
        
        _face_mesh_instance = _mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            static_image_mode=False
        )

class FaceEngine:
    """Optimized face recognition and liveness detection engine"""
    
    def __init__(self):
        # Initialize MediaPipe if not already initialized
        _init_mediapipe()
        
        # Load face encodings from cache (normalized)
        from face_cache import face_cache
        self.known_faces = {}
        
        try:
            all_faces = face_cache.get_all()
            for emp_id, enc in all_faces.items():
                if isinstance(enc, list):
                    vec = np.array(enc, dtype=np.float32)
                    norm = np.linalg.norm(vec)
                    if norm > 0:
                        vec = vec / norm
                    self.known_faces[emp_id] = vec
        except Exception as e:
            print(f"Error loading face cache: {e}")
            self.known_faces = {}
        
        # Thresholds from config
        self.recognition_threshold = Config.FACE_RECOGNITION_THRESHOLD
        self.liveness_threshold = Config.LIVENESS_THRESHOLD
        self.min_face_confidence = Config.MIN_FACE_CONFIDENCE
    
    def _extract_face_embedding(self, img_rgb: np.ndarray) -> Optional[np.ndarray]:
        """
        Extract face embedding using MediaPipe FaceMesh
        
        Args:
            img_rgb: RGB image array
            
        Returns:
            128-D face embedding or None
        """
        try:
            global _face_mesh_instance
            
            if _face_mesh_instance is None:
                return None
            
            # Process with FaceMesh
            img_rgb.flags.writeable = False
            results = _face_mesh_instance.process(img_rgb)
            
            if not results.multi_face_landmarks:
                return None
            
            # Get the first face
            face_landmarks = results.multi_face_landmarks[0]
            
            # Extract key landmarks for face embedding
            key_indices = [
                33, 133, 157, 158, 159, 160,  # Left eye
                362, 263, 386, 387, 388, 389,  # Right eye
                1, 2, 3, 4, 5, 6, 168, 197,    # Nose
                61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375,  # Mouth
                57, 58, 76, 77, 90, 91, 103, 104  # Jawline
            ]
            
            embedding = []
            for idx in key_indices:
                if idx < len(face_landmarks.landmark):
                    lm = face_landmarks.landmark[idx]
                    embedding.extend([lm.x, lm.y, lm.z])
            
            # Ensure 128 dimensions
            embedding_array = np.array(embedding, dtype=np.float32)
            
            if len(embedding_array) < 128:
                embedding_array = np.pad(embedding_array, (0, 128 - len(embedding_array)))
            elif len(embedding_array) > 128:
                embedding_array = embedding_array[:128]
            
            # Normalize the embedding
            norm = np.linalg.norm(embedding_array)
            if norm > 0:
                embedding_array = embedding_array / norm
            
            return embedding_array
            
        except Exception as e:
            print(f"Error extracting face embedding: {e}")
            return None
    
    def _calculate_eye_aspect_ratio(self, landmarks) -> float:
        """
        Calculate Eye Aspect Ratio for liveness detection
        
        Args:
            landmarks: MediaPipe face landmarks
            
        Returns:
            float: Average Eye Aspect Ratio
        """
        try:
            # Left eye landmarks (indices from MediaPipe)
            left_eye_vertical = abs(landmarks[159].y - landmarks[145].y)
            left_eye_horizontal = abs(landmarks[33].x - landmarks[133].x)
            left_ear = left_eye_vertical / (left_eye_horizontal + 1e-6)
            
            # Right eye landmarks
            right_eye_vertical = abs(landmarks[386].y - landmarks[374].y)
            right_eye_horizontal = abs(landmarks[362].x - landmarks[263].x)
            right_ear = right_eye_vertical / (right_eye_horizontal + 1e-6)
            
            # Average EAR
            return (left_ear + right_ear) / 2.0
            
        except Exception as e:
            print(f"Error calculating EAR: {e}")
            return 0.0
    
    def process_attendance(self, image: np.ndarray) -> dict:
        import cv2
        """
        Process attendance image for face recognition and liveness detection
        
        Args:
            image: numpy array image (BGR format)
            
        Returns:
            dict: {
                'employee_id': int or None,
                'similarity': float,
                'liveness_ok': bool
            }
        """
        try:
            # Convert BGR to RGB
            img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            img_rgb.flags.writeable = False
            
            # Process with MediaPipe
            global _face_mesh_instance
            if _face_mesh_instance is None:
                return {
                    'employee_id': None,
                    'similarity': 0.0,
                    'liveness_ok': False
                }
            
            results = _face_mesh_instance.process(img_rgb)
            
            # Check if face detected
            if not results.multi_face_landmarks:
                return {
                    'employee_id': None,
                    'similarity': 0.0,
                    'liveness_ok': False
                }
            
            # Get face landmarks
            landmarks = results.multi_face_landmarks[0].landmark
            
            # Step 1: Liveness detection
            ear = self._calculate_eye_aspect_ratio(landmarks)
            liveness_ok = ear > self.liveness_threshold
            
            if not liveness_ok:
                return {
                    'employee_id': None,
                    'similarity': 0.0,
                    'liveness_ok': False
                }
            
            # Step 2: Extract face embedding
            face_embedding = self._extract_face_embedding(img_rgb)
            if face_embedding is None:
                return {
                    'employee_id': None,
                    'similarity': 0.0,
                    'liveness_ok': True
                }
            
            # Step 3: Recognize face
            best_match_id = None
            best_similarity = 0.0
            
            for emp_id, known_vector in self.known_faces.items():
                # Calculate cosine similarity
                similarity = float(np.dot(face_embedding, known_vector))
                
                if similarity > best_similarity and similarity > self.recognition_threshold:
                    best_similarity = similarity
                    best_match_id = emp_id
            
            return {
                'employee_id': best_match_id,
                'similarity': best_similarity,
                'liveness_ok': True
            }
            
        except Exception as e:
            print(f"Error in process_attendance: {e}")
            return {
                'employee_id': None,
                'similarity': 0.0,
                'liveness_ok': False
            }
    
    def verify_liveness(self, image: np.ndarray) -> bool:
        """
        Verify liveness from image
        
        Args:
            image: numpy array image (BGR)
            
        Returns:
            bool: True if live, False otherwise
        """
        try:
            img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            img_rgb.flags.writeable = False
            
            global _face_mesh_instance
            if _face_mesh_instance is None:
                return False
            
            results = _face_mesh_instance.process(img_rgb)
            
            if not results.multi_face_landmarks:
                return False
            
            landmarks = results.multi_face_landmarks[0].landmark
            ear = self._calculate_eye_aspect_ratio(landmarks)
            
            return ear > self.liveness_threshold
            
        except Exception as e:
            print(f"Error in verify_liveness: {e}")
            return False
    
    def extract_face_encoding(self, image_bytes: bytes) -> Optional[list]:
        """
        Extract 128-D face encoding from image bytes
        
        Args:
            image_bytes: Image data in bytes
            
        Returns:
            List of 128 floats or None if no face detected
        """
        try:
            # Decode image
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                return None
            
            # Extract embedding
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            embedding = self._extract_face_embedding(img_rgb)
            
            if embedding is None:
                return None
            
            return embedding.tolist()
            
        except Exception as e:
            print(f"Error in extract_face_encoding: {e}")
            return None
    
    
    def add_face_encoding(self, employee_id: int, encoding: list):
        """
        Add face encoding to cache and memory
        
        Args:
            employee_id: Employee ID
            encoding: Face encoding list
        """
        try:
            from face_cache import face_cache
            
            encoding_array = np.array(encoding, dtype=np.float32)
            norm = np.linalg.norm(encoding_array)
            if norm > 0:
                encoding_array = encoding_array / norm
            
            # Save to cache
            face_cache.add(employee_id, encoding_array.tolist())
            
            # Save to memory
            self.known_faces[employee_id] = encoding_array
            
            print(f"[FaceEngine] Added encoding for employee {employee_id}")
            
        except Exception as e:
            print(f"[FaceEngine] Failed to add encoding: {e}")
    
    def get_stats(self):
        """Get face engine statistics"""
        return {
            'total_faces': len(self.known_faces),
            'recognition_threshold': self.recognition_threshold,
            'liveness_threshold': self.liveness_threshold,
            'cache_file_exists': os.path.exists(Config.FACE_CACHE_FILE)
        }
# Global face engine (lazy safe)
face_engine = None

def get_face_engine_safe():
    global face_engine
    if face_engine is None:
        face_engine = get_face_engine()
    return face_engine
