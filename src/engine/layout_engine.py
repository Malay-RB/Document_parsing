# class LayoutEngine:

#     # receives the layout_predictor model
#     def __init__(self, predictor):
#         self.predictor = predictor

#     # surya layout detection model expects list of images but we pass a single image so in order to read a single image we use [0] as index
#     def detect(self, image):

#         layout = self.predictor([image])[0]

#         # returns coordinates, label, confidence
#         return layout.bboxes

# src/engine/layout_engine.py

from processing.logger import logger

class LayoutEngine:
    def __init__(self, factory):
        """Expects the global PipelineFactory instance."""
        self.factory = factory

    def detect(self, image, model_name="surya_layout"):
       
        try:
            # wrapper instantiation
            engine = self.factory.get_model(model_name)
            # model load and execution
            return engine.execute(image=image)
        except Exception as e:
            logger.error(f"Layout detection failed for {model_name}: {e}")
            return []