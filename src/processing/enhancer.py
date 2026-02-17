import torch
from super_image import ImageLoader


class ImageEnhancer:

    def __init__(self, sr_model):
        self.sr_model = sr_model


    def enhance_crop(self, crop):

        if crop.width > 1200 or crop.height > 1200:
            return crop

        inputs = ImageLoader.load_image(crop)

        with torch.no_grad():
            preds = self.sr_model(inputs)

        return ImageLoader.convert_to_pil(preds)
