from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.schemas.metadata_schema import GetImageSchema


router = APIRouter()



@router.post("/get_updated_image")
async def chat(image_data: GetImageSchema):
    try:
        new_path = update_image_metadata(
            image_path=image_data.image_url,
            output_data=image_data.metadata.model_dump(exclude_none=True),
            cloudinary=cloudinary
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": True,
                "status_code": 200,
                "updated_image_url": new_path})    
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": False,
                "status_code": 500,
                "error": str(e)})

    