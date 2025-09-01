import type { Request, Response } from "express";
import { validationResult } from "express-validator";
import jwt from "jsonwebtoken";
import User from "../models/User.model";
import { sendOTP } from "../services/email.service";
import { OAuth2Client } from "google-auth-library";

const googleClient = new OAuth2Client(process.env.GOOGLE_CLIENT_ID);

const generateOTP = () => {
  return Math.floor(100000 + Math.random() * 900000).toString();
};

const generateToken = (userId: string) => {
  return jwt.sign({ userId }, process.env.JWT_SECRET as string, {
    expiresIn: process.env.JWT_EXPIRE as jwt.SignOptions["expiresIn"],
  });
};

export const signup = async (req: Request, res: Response) => {
  try {
    const errors = validationResult(req);
    if (!errors.isEmpty()) {
      return res.status(400).json({ errors: errors.array() });
    }

    const { email, name, dateOfBirth, password } = req.body;

    const existingUser = await User.findOne({ email });
    if (existingUser) {
      return res.status(400).json({ error: "User already exists" });
    }

    const otp = generateOTP();
    const otpExpiry = new Date(Date.now() + 10 * 60 * 1000); // 10 minutes

    const user = new User({
      email,
      name,
      dateOfBirth,
      password,
      otp,
      otpExpiry,
    });

    await user.save();
    await sendOTP(email, otp);

    res.status(201).json({
      message: "OTP sent to your email",
      userId: user._id,
    });
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: "Failed to create account" });
  }
};

export const verifyOTP = async (req: Request, res: Response) => {
  try {
    const { userId, otp } = req.body;

    const user = await User.findById(userId);
    if (!user) {
      return res.status(404).json({ error: "User not found" });
    }

    if (user.otp !== otp || !user.otpExpiry || user.otpExpiry < new Date()) {
      return res.status(400).json({ error: "Invalid or expired OTP" });
    }

    user.isVerified = true;
    user.otp = undefined;
    user.otpExpiry = undefined;
    await user.save();

    const token = generateToken(user._id!.toString());

    res.json({
      token,
      user: {
        id: user._id,
        email: user.email,
        name: user.name,
      },
    });
  } catch (error) {
    res.status(500).json({ error: "Failed to verify OTP" });
  }
};

export const signin = async (req: Request, res: Response) => {
  try {
    const { email } = req.body;

    const user = await User.findOne({ email });
    if (!user) {
      return res.status(404).json({ error: "User not found" });
    }

    const otp = generateOTP();
    const otpExpiry = new Date(Date.now() + 10 * 60 * 1000);

    user.otp = otp;
    user.otpExpiry = otpExpiry;
    await user.save();

    await sendOTP(email, otp);

    res.json({
      message: "OTP sent to your email",
      userId: user._id,
    });
  } catch (error) {
    res.status(500).json({ error: "Failed to send OTP" });
  }
};

export const googleAuth = async (req: Request, res: Response) => {
  try {
    const { token } = req.body;

    const ticket = await googleClient.verifyIdToken({
      idToken: token,
      audience: process.env.GOOGLE_CLIENT_ID,
    });

    const payload = ticket.getPayload();
    if (!payload) {
      return res.status(400).json({ error: "Invalid token" });
    }

    let user = await User.findOne({ email: payload.email });

    if (!user) {
      user = new User({
        email: payload.email,
        name: payload.name,
        googleId: payload.sub,
        isVerified: true,
      });
      await user.save();
    }

    const jwtToken = generateToken(user._id!.toString());

    res.json({
      token: jwtToken,
      user: {
        id: user._id,
        email: user.email,
        name: user.name,
      },
    });
  } catch (error) {
    res.status(500).json({ error: "Google authentication failed" });
  }
};

export const resendOTP = async (req: Request, res: Response) => {
  try {
    const { userId } = req.body;

    const user = await User.findById(userId);
    if (!user) {
      return res.status(404).json({ error: "User not found" });
    }

    const otp = generateOTP();
    const otpExpiry = new Date(Date.now() + 10 * 60 * 1000);

    user.otp = otp;
    user.otpExpiry = otpExpiry;
    await user.save();

    await sendOTP(user.email, otp);

    res.json({ message: "OTP resent successfully" });
  } catch (error) {
    res.status(500).json({ error: "Failed to resend OTP" });
  }
};
