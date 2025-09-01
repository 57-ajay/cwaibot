import { Router } from "express";
import { body } from "express-validator";
import * as authController from "../controllers/auth.controller";

const router = Router();

router.post(
  "/signup",
  [
    body("email").isEmail().normalizeEmail(),
    body("name").trim().notEmpty(),
    body("dateOfBirth").optional().isISO8601(),
    body("password").optional().isLength({ min: 6 }),
  ],
  authController.signup,
);

router.post("/verify-otp", authController.verifyOTP);
router.post("/signin", authController.signin);
router.post("/google", authController.googleAuth);
router.post("/resend-otp", authController.resendOTP);

export default router;
