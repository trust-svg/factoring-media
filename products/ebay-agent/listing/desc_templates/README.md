# Description Templates

Place HTML description templates here as `{name}.html`.

The placeholder `{description}` is replaced with the AI-generated content.

## Setup

1. Copy your eBay Seller Hub description template HTML
2. Save it as `001.html` (matching your template name)
3. Put `{description}` where the product description should appear

## Example: 001.html

```html
<div style="font-family: Arial, sans-serif; max-width: 800px;">
  <img src="your-banner.jpg" width="100%">
  {description}
  <hr>
  <p>Thank you for shopping with us!</p>
</div>
```

If no template file is found, the AI-generated description is used as-is.
